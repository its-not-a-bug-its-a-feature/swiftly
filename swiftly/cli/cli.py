"""
Contains the CLI class that handles the original command line.
"""
"""
Copyright 2011-2013 Gregory Holt

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import functools
import os
import sys
import tempfile
import textwrap
import time
import traceback

from swiftly import VERSION
from swiftly.cli.context import CLIContext
from swiftly.cli.iomanager import IOManager
from swiftly.cli.optionparser import OptionParser
from swiftly.client import ClientManager, DirectClient, StandardClient


#: The list of CLICommand classes avaiable to CLI. You'll want to add any new
#: CLICommand you create to this list.
COMMANDS = [
    'swiftly.cli.auth.CLIAuth',
    'swiftly.cli.decrypt.CLIDecrypt',
    'swiftly.cli.delete.CLIDelete',
    'swiftly.cli.encrypt.CLIEncrypt',
    'swiftly.cli.fordo.CLIForDo',
    'swiftly.cli.get.CLIGet',
    'swiftly.cli.head.CLIHead',
    'swiftly.cli.help.CLIHelp',
    'swiftly.cli.ping.CLIPing',
    'swiftly.cli.post.CLIPost',
    'swiftly.cli.put.CLIPut',
    'swiftly.cli.tempurl.CLITempURL',
    'swiftly.cli.trans.CLITrans']


class CLI(object):
    """
    Handles the original command line.

    An example script is `swiftly` itself::

        #!/usr/bin/env python
        import sys
        import swiftly.cli
        sys.exit(swiftly.cli.CLI()())

    See the output of ``swiftly help`` for more information.
    """

    def __init__(self):
        #: The overall CLIContext containing attributes generated by the
        #: initial main_options parsing.
        #:
        #: The available attributes are:
        #:
        #: ==============  ====================================================
        #: cdn             True if the CDN URL should be used instead of the
        #:                 default Storage URL.
        #: client_manager  The :py:class:`swiftly.client.manager.ClientManager`
        #:                 to use for obtaining clients.
        #: concurrency     Number of concurrent actions to allow.
        #: io_manager      The :py:class:`swiftly.cli.iomanager.IOManager` to
        #:                 use for input and output.
        #: eventlet        True if Eventlet is in use.
        #: original_args   The original args used by the CLI.
        #: original_begin  The original time.time() when the CLI was called.
        #: verbose         Function to call when you want to (optionally) emit
        #:                 verbose output. ``verbose(msg, *args)`` where the
        #:                 output will be constructed with ``msg % args``.
        #: verbosity       Level of verbosity. Just None or 1 right now.
        #: ==============  ====================================================
        self.context = CLIContext()
        self.context.verbose = None
        self.context.io_manager = IOManager()

        #: A dictionary of the available commands and their CLICommand
        #: instances.
        self.commands = {}
        for command in COMMANDS:
            mod, cls = command.rsplit('.', 1)
            cls = getattr(__import__(mod, fromlist=[cls]), cls)
            inst = cls(self)
            self.commands[inst.name] = inst

        #: The main :py:class:`OptionParser`.
        self.option_parser = OptionParser(
            version=VERSION,
            usage='Usage: %prog [options] <command> [command_options] [args]',
            io_manager=self.context.io_manager)
        self.option_parser.add_option(
            '-h', dest='help', action='store_true',
            help='Shows this help text.')
        self.option_parser.add_option(
            '-A', '--auth-url', dest='auth_url',
            default=os.environ.get('SWIFTLY_AUTH_URL', ''), metavar='URL',
            help='URL to auth system, example: '
                 'http://127.0.0.1:8080/auth/v1.0 You can also set this with '
                 'the environment variable SWIFTLY_AUTH_URL.')
        self.option_parser.add_option(
            '-U', '--auth-user', dest='auth_user',
            default=os.environ.get('SWIFTLY_AUTH_USER', ''), metavar='USER',
            help='User name for auth system, example: test:tester You can '
                 'also set this with the environment variable '
                 'SWIFTLY_AUTH_USER.')
        self.option_parser.add_option(
            '-K', '--auth-key', dest='auth_key',
            default=os.environ.get('SWIFTLY_AUTH_KEY', ''), metavar='KEY',
            help='Key for auth system, example: testing You can also set this '
                 'with the environment variable SWIFTLY_AUTH_KEY.')
        self.option_parser.add_option(
            '-T', '--auth-tenant', dest='auth_tenant',
            default=os.environ.get('SWIFTLY_AUTH_TENANT', ''),
            metavar='TENANT',
            help='Tenant name for auth system, example: test You can '
                 'also set this with the environment variable '
                 'SWIFTLY_AUTH_TENANT. If not specified and needed, the auth '
                 'user will be used.')
        self.option_parser.add_option(
            '--auth-methods', dest='auth_methods',
            default=os.environ.get('SWIFTLY_AUTH_METHODS', ''),
            metavar='name[,name[...]]',
            help='Auth methods to use with the auth system, example: '
                 'auth2key,auth2password,auth2password_force_tenant,auth1 You '
                 'can also set this with the environment variable '
                 'SWIFTLY_AUTH_METHODS. Swiftly will try to determine the '
                 'best order for you; but if you notice it keeps making '
                 'useless auth attempts and that drives you crazy, you can '
                 'override that here. All the available auth methods are '
                 'listed in the example.')
        self.option_parser.add_option(
            '--region', dest='region',
            default=os.environ.get('SWIFTLY_REGION', ''), metavar='VALUE',
            help='Region to use, if supported by auth, example: DFW You can '
                 'also set this with the environment variable SWIFTLY_REGION. '
                 'Default: default region specified by the auth response.')
        self.option_parser.add_option(
            '-D', '--direct', dest='direct',
            default=os.environ.get('SWIFTLY_DIRECT', ''), metavar='PATH',
            help='Uses direct connect method to access Swift. Requires access '
                 'to rings and backend servers. The PATH is the account '
                 'path, example: /v1/AUTH_test You can also set this with the '
                 'environment variable SWIFTLY_DIRECT.')
        self.option_parser.add_option(
            '-P', '--proxy', dest='proxy',
            default=os.environ.get('SWIFTLY_PROXY', ''), metavar='URL',
            help='Uses the given proxy URL. You can also set this with the '
                 'environment variable SWIFTLY_PROXY.')
        self.option_parser.add_option(
            '-S', '--snet', dest='snet', action='store_true',
            default=os.environ.get('SWIFTLY_SNET', 'false').lower() == 'true',
            help='Prepends the storage URL host name with "snet-". Mostly '
                 'only useful with Rackspace Cloud Files and Rackspace '
                 'ServiceNet. You can also set this with the environment '
                 'variable SWIFTLY_SNET (set to "true" or "false").')
        self.option_parser.add_option(
            '-R', '--retries', dest='retries',
            default=int(os.environ.get('SWIFTLY_RETRIES', 4)),
            metavar='INTEGER',
            help='Indicates how many times to retry the request on a server '
                 'error. Default: 4. You can also set this with the '
                 'environment variable SWIFTLY_RETRIES.')
        self.option_parser.add_option(
            '-C', '--cache-auth', dest='cache_auth', action='store_true',
            default=(os.environ.get(
                'SWIFTLY_CACHE_AUTH', 'false').lower() == 'true'),
            help='If set true, the storage URL and auth token are cached in '
                 'your OS temporary directory as <user>.swiftly for reuse. If '
                 'there are already cached values, they are used without '
                 'authenticating first. You can also set this with the '
                 'environment variable SWIFTLY_CACHE_AUTH (set to "true" or '
                 '"false").')
        self.option_parser.add_option(
            '--cdn', dest='cdn', action='store_true',
            help='Directs requests to the CDN management interface.')
        self.option_parser.add_option(
            '--concurrency', dest='concurrency',
            default=int(os.environ.get('SWIFTLY_CONCURRENCY', 1)),
            metavar='INTEGER',
            help='Sets the the number of actions that can be done '
                 'simultaneously when possible (currently requires using '
                 'Eventlet too). Default: 1. You can also set this with the '
                 'environment variable SWIFTLY_CONCURRENCY. Note that some '
                 'nested actions may amplify the number of concurrent '
                 'actions. For instance, a put of an entire directory will '
                 'use up to this number of concurrent actions. A put of a '
                 'segmented object will use up to this number of concurrent '
                 'actions. But, if a directory structure put is uploading '
                 'segmented objects, this nesting could cause up to INTEGER * '
                 'INTEGER concurrent actions.')
        self.option_parser.add_option(
            '--eventlet', dest='eventlet', action='store_true',
            help='Enables Eventlet, if installed. This is disabled by default '
                 'if Eventlet is not installed or is less than version 0.11.0 '
                 '(because older Swiftly+Eventlet tends to use excessive CPU.')
        self.option_parser.add_option(
            '--no-eventlet', dest='no_eventlet', action='store_true',
            help='Disables Eventlet, even if installed and version 0.11.0 or '
                 'greater.')
        self.option_parser.add_option(
            '-v', '--verbose', dest='verbose', action='store_true',
            help='Causes output to standard error indicating actions being '
                 'taken. These output lines will be prefixed with VERBOSE and '
                 'will also include the number of seconds elapsed since '
                 'Swiftly started.')

        self.option_parser.raw_epilog = 'Commands:\n'
        for name in sorted(self.commands):
            command = self.commands[name]
            lines = command.option_parser.get_usage().split('\n')
            main_line = '  ' + lines[0].split(']', 1)[1].strip()
            for x in xrange(4):
                lines.pop(0)
            for x, line in enumerate(lines):
                if not line:
                    lines = lines[:x]
                    break
            if len(main_line) < 24:
                initial_indent = main_line + ' ' * (24 - len(main_line))
            else:
                self.option_parser.raw_epilog += main_line + '\n'
                initial_indent = ' ' * 24
            self.option_parser.raw_epilog += textwrap.fill(
                ' '.join(lines), width=79, initial_indent=initial_indent,
                subsequent_indent=' ' * 24) + '\n'

    def __call__(self, args=None):
        self.context.original_begin = time.time()
        self.context.original_args = args if args is not None else sys.argv[1:]
        self.option_parser.disable_interspersed_args()
        try:
            options, args = self.option_parser.parse_args(
                self.context.original_args)
        except UnboundLocalError:
            # Happens sometimes with an error handler that doesn't raise its
            # own exception. We'll catch the error below with
            # error_encountered.
            pass
        self.option_parser.enable_interspersed_args()
        if self.option_parser.error_encountered:
            return 1
        if options.version:
            self.option_parser.print_version()
            return 1
        if not args or options.help:
            self.option_parser.print_help()
            return 1
        self.context.original_main_args = self.context.original_args[
            :-len(args)]

        self.context.eventlet = None
        if options.eventlet:
            self.context.eventlet = True
        if options.no_eventlet:
            self.context.eventlet = False
        if self.context.eventlet is None:
            self.context.eventlet = False
            try:
                import eventlet
                # Eventlet 0.11.0 fixed the CPU bug
                if eventlet.__version__ >= '0.11.0':
                    self.context.eventlet = True
            except ImportError:
                pass

        subprocess_module = None
        if self.context.eventlet:
            try:
                import eventlet.green.subprocess
                subprocess_module = eventlet.green.subprocess
            except ImportError:
                pass
        if subprocess_module is None:
            import subprocess
            subprocess_module = subprocess
        self.context.io_manager.subprocess_module = subprocess_module

        if options.verbose:
            self.context.verbosity = 1
            self.context.verbose = self._verbose
            self.context.io_manager.verbose = functools.partial(
                self._verbose, skip_sub_command=True)

        options.retries = int(options.retries)
        if options.direct:
            self.context.client_manager = ClientManager(
                DirectClient, swift_proxy_storage_path=options.direct,
                attempts=options.retries + 1, eventlet=self.context.eventlet,
                verbose=self._verbose)
        else:
            auth_cache_path = None
            if options.cache_auth:
                auth_cache_path = os.path.join(
                    tempfile.gettempdir(),
                    '%s.swiftly' % os.environ.get('USER', 'user'))
            self.context.client_manager = ClientManager(
                StandardClient, auth_methods=options.auth_methods,
                auth_url=options.auth_url, auth_tenant=options.auth_tenant,
                auth_user=options.auth_user, auth_key=options.auth_key,
                auth_cache_path=auth_cache_path, region=options.region,
                snet=options.snet, attempts=options.retries + 1,
                eventlet=self.context.eventlet, verbose=self._verbose)

        self.context.cdn = options.cdn
        self.context.concurrency = int(options.concurrency)

        command = args[0]
        if command == 'for':
            command = 'fordo'
        if command not in self.commands:
            with self.context.io_manager.with_stderr() as fp:
                fp.write('ERROR unknown command %r\n' % args[0])
                fp.flush()
            return 1
        try:
            self.commands[command](args[1:])
        except Exception as err:
            if hasattr(err, 'text'):
                if err.text:
                    with self.context.io_manager.with_stderr() as fp:
                        fp.write('ERROR ')
                        fp.write(err.text)
                        fp.write('\n')
                        fp.flush()
            else:
                with self.context.io_manager.with_stderr() as fp:
                    fp.write(traceback.format_exc())
                    fp.write('\n')
                    fp.flush()
            return getattr(err, 'code', 1)
        return 0

    def _verbose(self, msg, *args, **kwargs):
        if self.context.verbosity:
            skip_sub_command = kwargs.get('skip_sub_command', False)
            with self.context.io_manager.with_debug(
                    skip_sub_command=skip_sub_command) as fp:
                try:
                    fp.write(
                        'VERBOSE %.02f ' %
                        (time.time() - self.context.original_begin))
                    fp.write(msg % args)
                except TypeError as err:
                    raise TypeError('%s: %r %r' % (err, msg, args))
                fp.write('\n')
                fp.flush()
