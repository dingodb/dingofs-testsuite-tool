"""Opt-in test transport: never shipped in the immutable runtime package."""
import sys

if sys.argv[0].endswith('run_tests.py'):
    import atexit
    import errno
    import importlib.util
    import json
    import os
    from pathlib import Path
    import shlex
    import shutil
    import socket
    from types import SimpleNamespace

    sys.path.insert(0, '/dingofs-integration-test')
    import paramiko

    home = Path(os.environ['HOME'])
    assert home == Path('/functional-home') and home.stat().st_uid == os.geteuid()
    assert not os.environ.get('SSH_AUTH_SOCK')
    # A writable private HOME and even hostile local alias config must not
    # affect context-pinned Paramiko routing or authentication.
    (home / '.ssh').mkdir()
    (home / '.ssh/config').write_text('Host *\n  HostName 203.0.113.9\n  Port 99\n'
                                     '  User wrong-user\n  ProxyCommand false\n')
    for readonly in ('/functional-runtime/functional_runtime.py',
                     '/dingofs-integration-test/src/config/env_parser.py'):
        try:
            descriptor = os.open(readonly, os.O_WRONLY | os.O_APPEND)
        except OSError as error:
            assert error.errno == errno.EROFS
        else:
            os.close(descriptor)
            raise AssertionError('Installed runtime source is not mounted read-only')

    def denied(*args, **kwargs):
        raise AssertionError('Real network access is forbidden by integration test')

    socket.socket.connect = denied
    socket.getaddrinfo = denied
    spec = importlib.util.spec_from_file_location('owned_remote_fixture', '/test-transport/owned_remote.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    remote = fixture.Remote()
    connections = []

    class Channel:
        def __init__(self, result):
            self.code, out, err = result
            self.out, self.err = out.encode(), err.encode()

        def recv_ready(self): return bool(self.out)
        def recv_stderr_ready(self): return bool(self.err)
        def recv(self, size):
            value, self.out = self.out[:size], self.out[size:]
            return value
        def recv_stderr(self, size):
            value, self.err = self.err[:size], self.err[size:]
            return value
        def exit_status_ready(self): return True
        def recv_exit_status(self): return self.code
        def close(self): pass

    class Client:
        def set_missing_host_key_policy(self, policy): pass
        def connect(self, **kwargs):
            assert kwargs['hostname'] in ('192.0.2.1', '192.0.2.2')
            assert kwargs['port'] == 2222 and kwargs['username'] == 'tester'
            assert kwargs['password'] == 'fixture-secret'
            assert kwargs['look_for_keys'] is False and kwargs['allow_agent'] is False
            assert 'key_filename' not in kwargs and 'sock' not in kwargs
            self.host = kwargs['hostname']
            connections.append({k: kwargs[k] for k in ('hostname', 'port', 'username', 'look_for_keys', 'allow_agent')})
        def get_transport(self):
            return SimpleNamespace(set_keepalive=lambda seconds: None,
                                   is_active=lambda: True, is_authenticated=lambda: True)
        def exec_command(self, command, timeout=None):
            words = shlex.split(command)
            if words[:1] == ['sudo']:
                assert words[:7] == ['sudo', '-n', '-u', 'tester', '--', 'bash', '-lc']
                command = words[7]
            channel = Channel(remote(None, self.host, command))
            return None, SimpleNamespace(channel=channel), SimpleNamespace(channel=channel)
        def close(self): pass

    paramiko.SSHClient = Client
    original_which = shutil.which
    shutil.which = lambda name, *args, **kwargs: None if name == 'allure' else original_which(name, *args, **kwargs)

    def record():
        Path('/output/transport.json').write_text(json.dumps({
            'connections': connections, 'command_count': len(remote.commands),
            'remaining_filesystems': remote.filesystems,
            'remaining_mounts': list(remote.mounts), 'remaining_directories': remote.directories,
        }))
    atexit.register(record)
