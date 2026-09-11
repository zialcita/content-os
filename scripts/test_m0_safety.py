#!/usr/bin/env python3
"""Synthetic M0 configuration-isolation regression tests (no live configuration).

Run with .venv/bin/python -B -m unittest discover -s scripts -p test_m0_safety.py -v.
Every application/script import happens in a subprocess with a constructed env,
inside a temporary source-only checkout. Never inspect/copy a real .env, inherit
application environment, start app lifespan, or contact a provider/database host.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv/bin/python'
POISON_KEY = 'synthetic-dotenv-key-not-a-credential'


class M0SafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='m0-safety-', dir='/tmp')
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name)
        self.repo = self.temp / 'checkout'
        (self.repo / 'scripts').mkdir(parents=True)
        (self.repo / 'backend').mkdir()
        # Only application source code, never dotenv/data/credentials or caches.
        for source in (ROOT / 'backend').rglob('*.py'):
            if '__pycache__' in source.parts:
                continue
            destination = self.repo / 'backend' / source.relative_to(ROOT / 'backend')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for name in ['m0_test_bootstrap.py', 'snapshot_m0.py', 'verify_m0.py']:
            shutil.copyfile(ROOT / 'scripts' / name, self.repo / 'scripts' / name)
        self.cwd = self.temp / 'ambient' / 'work'
        self.cwd.mkdir(parents=True)
        self.poison_databases = [self.temp / 'parent-poison.db', self.temp / 'cwd-poison.db']
        for directory, database, label in zip(
                [self.cwd.parent, self.cwd], self.poison_databases, ['parent', 'cwd']):
            (directory / '.env').write_text(
                'DATABASE_URL=sqlite:///' + str(database) + '\n'
                'AI_API_KEY=' + POISON_KEY + '\n'
                'APP_ENV=synthetic-' + label + '-poison\n'
                'AVATAR_ENGINE=synthetic-live-poison\n', encoding='utf-8')

    def environment(self, **values):
        # Deliberately no os.environ/getenv/copy: only constructed values.
        return dict({
            'PATH': os.defpath,
            'HOME': str(self.temp),
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONNOUSERSITE': '1',
        }, **values)

    def run_python(self, code, env=None):
        result = subprocess.run(
            [str(PYTHON), '-B', '-c', textwrap.dedent(code)],
            cwd=self.cwd, env=self.environment() if env is None else env,
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_no_poison_database(self):
        for path in self.poison_databases:
            self.assertFalse(path.exists(), 'Synthetic ambient database was opened: ' + str(path))

    def test_positive_control_constructed_dotenv_really_loads(self):
        """Prove poisoning is effective, without creating an engine/connection."""
        self.run_python(f'''
            import sys
            sys.path.insert(0, {str(self.repo / 'backend')!r})
            from config import Settings
            settings = Settings()
            assert settings.ai_api_key == {POISON_KEY!r}
            assert settings.app_env == 'synthetic-cwd-poison'
            assert settings.database_url == {'sqlite:///' + str(self.poison_databases[1])!r}
        ''')
        # Test the parent dotenv independently, not merely an overridden value.
        (self.cwd / '.env').unlink()
        self.run_python(f'''
            import sys
            sys.path.insert(0, {str(self.repo / 'backend')!r})
            from config import Settings
            assert Settings().app_env == 'synthetic-parent-poison'
        ''')
        self.assert_no_poison_database()

    def test_bootstrap_disables_dotenv_and_clears_preexisting_settings_cache(self):
        self.run_python(f'''
            import runpy, sys
            sys.path.insert(0, {str(self.repo / 'backend')!r})
            from config import Settings, get_settings
            assert get_settings().ai_api_key == {POISON_KEY!r}
            runpy.run_path({str(self.repo / 'scripts/m0_test_bootstrap.py')!r})
            assert Settings.model_config['env_file'] is None
            assert get_settings().ai_api_key == ''
            assert get_settings().app_env == 'test'
            from database import engine
            assert str(engine.url) == 'sqlite:///:memory:'
        ''', self.environment(APP_ENV='test', DATABASE_URL='sqlite:///:memory:'))
        self.assert_no_poison_database()

    def test_bootstrap_cli_disables_dotenv_before_pytest_collection(self):
        test = self.cwd / 'test_collection.py'
        test.write_text(textwrap.dedent('''
            from config import Settings, get_settings
            from database import engine
            # These run during collection, before pytest can invoke fixtures.
            assert Settings.model_config['env_file'] is None
            assert get_settings().ai_api_key == ''
            assert str(engine.url) == 'sqlite:///:memory:'
            def test_safe_collection():
                assert get_settings().avatar_engine == 'simulated'
        '''), encoding='utf-8')
        result = subprocess.run(
            [str(PYTHON), '-B', str(self.repo / 'scripts/m0_test_bootstrap.py'),
             str(test), '-q', '-p', 'no:cacheprovider'],
            cwd=self.cwd,
            env=self.environment(APP_ENV='test', DATABASE_URL='sqlite:///:memory:',
                                 PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'),
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 passed', result.stdout)
        self.assert_no_poison_database()

    def test_snapshot_disables_dotenv_before_real_app_import(self):
        # CWD/parent dotenv are outside the checkout's explicit refusal locations.
        # Run the real snapshot on source-only copies; all artifacts remain temp.
        self.run_python(f'''
            import runpy
            runpy.run_path({str(self.repo / 'scripts/snapshot_m0.py')!r}, run_name='__main__')
            from config import Settings, get_settings
            from database import engine
            from main import settings as app_settings
            assert Settings.model_config['env_file'] is None
            assert get_settings().ai_api_key == ''
            assert get_settings().avatar_engine == 'simulated'
            assert app_settings.app_env == 'test'
            assert str(engine.url) == 'sqlite:///:memory:'
        ''', self.environment(DATABASE_URL='sqlite:///' + str(self.poison_databases[0]),
                             AI_API_KEY='synthetic-ambient-key', APP_ENV='synthetic-ambient'))
        evidence = self.repo / 'docs/evidence/m0'
        self.assertTrue(json.loads((evidence / 'legacy.openapi.json').read_text())['paths'])
        self.assertTrue(json.loads((evidence / 'legacy.schema.json').read_text()))
        self.assertIn('CREATE TABLE', (evidence / 'legacy.schema.sql').read_text())
        self.assert_no_poison_database()

    def test_disposable_runner_passes_selected_database_not_ambient(self):
        # Invoke actual runner.main and its real bootstrap/pytest subprocess.
        # Substitute only tempfile's location (to poison both dotenv search dirs)
        # and Git metadata (not part of isolation; never consult checkout config).
        tests = self.repo / 'backend/tests'
        shutil.rmtree(tests)
        tests.mkdir()
        (tests / 'test_selected_database.py').write_text(textwrap.dedent('''
            from pathlib import Path
            from config import Settings, get_settings
            from database import engine
            from sqlalchemy import text
            def test_selected_database():
                selected = Path.cwd() / 'baseline.db'
                assert Settings.model_config['env_file'] is None
                assert get_settings().database_url == 'sqlite:///' + str(selected)
                assert engine.url.database == str(selected)
                assert get_settings().ai_api_key == ''
                assert get_settings().app_env == 'test'
                assert get_settings().avatar_engine == 'simulated'
                with engine.begin() as connection:
                    connection.execute(text('CREATE TABLE safety_probe (id INTEGER)'))
                assert selected.is_file()
        '''), encoding='utf-8')
        result = self.run_python(f'''
            import importlib.util
            from pathlib import Path
            import subprocess, tempfile
            from unittest.mock import patch
            spec = importlib.util.spec_from_file_location('runner', {str(self.repo / 'scripts/verify_m0.py')!r})
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            real_temporary_directory = tempfile.TemporaryDirectory
            real_run = subprocess.run
            def poisoned_temporary_directory(*args, **kwargs):
                kwargs['dir'] = {str(self.cwd.parent)!r}
                directory = real_temporary_directory(*args, **kwargs)
                (Path(directory.name) / '.env').write_text(
                    'DATABASE_URL=sqlite:///{str(self.poison_databases[1])}\\n'
                    'AI_API_KEY={POISON_KEY}\\nAVATAR_ENGINE=synthetic-live-poison\\n')
                return directory
            with patch.object(runner.tempfile, 'TemporaryDirectory', side_effect=poisoned_temporary_directory), \\
                 patch.object(runner.subprocess, 'run', wraps=real_run) as child, \\
                 patch.object(runner.subprocess, 'check_output', return_value='synthetic-commit\\n'):
                assert runner.main() == 0
                child.assert_called_once()
                args, kwargs = child.call_args
                selected = Path(kwargs['cwd']) / 'baseline.db'
                assert Path(args[0][0]).samefile({str(PYTHON)!r})
                assert args[0][1] == {str(self.repo / 'scripts/m0_test_bootstrap.py')!r}
                assert kwargs['env']['DATABASE_URL'] == 'sqlite:///' + str(selected)
                assert kwargs['env']['AI_API_KEY'] == ''
                assert kwargs['env']['APP_ENV'] == 'test'
                assert 'SYNTHETIC_AMBIENT_MARKER' not in kwargs['env']
                assert not selected.parent.exists(), 'Disposable DB must be cleaned up'
        ''', self.environment(DATABASE_URL='sqlite:///' + str(self.poison_databases[0]),
                             AI_API_KEY='synthetic-ambient-key', APP_ENV='synthetic-ambient',
                             SYNTHETIC_AMBIENT_MARKER='must-not-propagate'))
        self.assertIn('1 passed', result.stdout)
        self.assert_no_poison_database()


if __name__ == '__main__':
    unittest.main(verbosity=2)
