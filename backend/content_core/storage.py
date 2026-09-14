"""Private local storage for development. No public URL or caller-chosen path.

UUID namespaces, dirfd/O_NOFOLLOW walking, immutable part files, bounded reads.
Not a claim of S3, antivirus or production retention integration.
"""
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

PART_BYTES=8*1024*1024


class StorageError(Exception): pass
class StorageMissing(StorageError): pass


class LocalStore:
    mode='LOCAL_PRIVATE_DEVELOPMENT'
    def __init__(self, root, *, development=False):
        if not development: raise StorageError('Local store requires explicit development mode')
        self.root=Path(root)
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        st=os.fstat(self.fd)
        if st.st_uid!=os.geteuid() or st.st_mode & 0o077:
            os.close(self.fd);self.fd=None
            raise StorageError('Private store must be owner-only')

    def close(self):
        if self.fd is not None:
            os.close(self.fd); self.fd=None

    def directory(self,key,create=False):
        pieces=key.split('/')
        if len(pieces)!=3 or any(str(UUID(x))!=x for x in pieces): raise StorageError('Invalid object namespace')
        fd=os.dup(self.fd)
        try:
            for part in pieces:
                if create:
                    try: os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError: pass
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                st=os.fstat(nxt)
                if st.st_uid!=os.geteuid() or st.st_mode & 0o077:
                    os.close(nxt);raise OSError('Unsafe namespace permissions')
                os.close(fd); fd=nxt
            return fd
        except FileNotFoundError:
            os.close(fd)
            raise StorageMissing('Storage namespace absent') from None
        except (OSError,ValueError):
            os.close(fd)
            raise StorageError('Unsafe or absent storage path') from None

    def write_part(self,key,number,data):
        if not 1<=number<=256 or not 1<=len(data)<=PART_BYTES: raise StorageError('Invalid part')
        directory=self.directory(key,True)
        name=f'{number:04d}.part'
        tmp=f'.{uuid4().hex}.tmp'
        try:
            try:
                existing=self.read_part(key,number)
            except StorageError:
                existing=None
            if existing is not None:
                if existing!=data: raise StorageError('Part conflict')
                return
            fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                with os.fdopen(fd,'wb') as output:
                    output.write(data); output.flush(); os.fsync(output.fileno())
                try:
                    os.link(tmp,name,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
                except FileExistsError:
                    if self.read_part(key,number)!=data: raise StorageError('Part conflict')
                os.fsync(directory)
            finally:
                try: os.unlink(tmp,dir_fd=directory)
                except FileNotFoundError: pass
        except OSError:
            raise StorageError('Storage write refused') from None
        finally: os.close(directory)

    def read_part(self,key,number):
        directory=self.directory(key)
        try:
            fd=os.open(f'{number:04d}.part',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            import stat
            st=os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:
                os.close(fd);raise StorageError('Unsafe linked or non-regular part')
            with os.fdopen(fd,'rb') as source:
                data=source.read(PART_BYTES+1)
            if len(data)>PART_BYTES: raise StorageError('Oversized part')
            return data
        except OSError:
            raise StorageError('Part unavailable') from None
        finally: os.close(directory)

    def chunks(self,key,parts):
        for index,part in enumerate(parts or [],1):
            if part['part_number']!=index: raise StorageError('Noncontiguous parts')
            data=self.read_part(key,index)
            if len(data)!=part['size_bytes'] or hashlib.sha256(data).hexdigest()!=part['sha256']:
                raise StorageError('Part hash mismatch')
            yield data

    def purge(self,key):
        try: directory=self.directory(key)
        except StorageMissing: return
        try:
            for name in os.listdir(directory):
                # Never follow links, recurse, or delete a caller-specified namespace.
                if name.endswith('.part') or (name.startswith('.') and name.endswith('.tmp')):
                    os.unlink(name,dir_fd=directory)
        finally: os.close(directory)
