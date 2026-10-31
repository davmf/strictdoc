import argparse

from strictdoc.cli.argument_int_range import IntRange
from strictdoc.cli.base_command import BaseCommand, CLIValidationError
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.helpers.parallelizer import Parallelizer
from strictdoc.server.server import run_strictdoc_server


class ServerCommand(BaseCommand):
    HELP = "Run StrictDoc web server."
    DETAILED_HELP = HELP

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        command_parser_server = parser

        command_parser_server.add_argument("input_path")
        command_parser_server.add_argument("--output-path", type=str)
        command_parser_server.add_argument("--host", type=str)
        command_parser_server.add_argument("--port", type=IntRange(1024, 65000))
        # The --reload and --no-reload options are currently used only for
        # StrictDoc's own development. We may want to revisit this for the end
        # users in the future but for now they are excluded from the help
        # messages.
        command_parser_server.add_argument(
            "--reload",
            default=False,
            action="store_true",
            help=argparse.SUPPRESS,
        )
        command_parser_server.add_argument(
            "--no-reload",
            dest="reload",
            action="store_false",
            help=argparse.SUPPRESS,
        )
        command_parser_server.add_argument(
            "--watch",
            default=False,
            action="store_true",
            help=(
                "Watch project files and live-reload connected browsers when "
                "documents change on disk."
            ),
        )
        command_parser_server.add_argument(
            "--auth-proxy-user-header",
            type=str,
            help=(
                "Name of the request header in which an authenticating "
                "reverse proxy passes the signed-in user. When set, requests "
                "without it are rejected."
            ),
        )
        command_parser_server.add_argument(
            "--auth-proxy-email-header",
            type=str,
            help="Name of the request header with the user's email address.",
        )
        command_parser_server.add_argument(
            "--auth-proxy-name-header",
            type=str,
            help="Name of the request header with the user's display name.",
        )
        command_parser_server.add_argument(
            "--auth-proxy-groups-header",
            type=str,
            help=(
                "Name of the request header with the user's groups, "
                "comma-separated. Groups decide the user's role."
            ),
        )
        command_parser_server.add_argument(
            "--auth-editor-group",
            action="append",
            help="Group whose members can edit. Can be given more than once.",
        )
        command_parser_server.add_argument(
            "--auth-admin-group",
            action="append",
            help=(
                "Group whose members can edit and change grammars. Can be "
                "given more than once."
            ),
        )
        command_parser_server.add_argument(
            "--config",
            type=str,
            help="Path to the StrictDoc TOML config file.",
        )

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config: ServerCommandConfig = ServerCommandConfig(**vars(args))

    def run(self, parallelizer: Parallelizer) -> None:  # noqa: ARG002
        server_config = self.config
        try:
            server_config.validate()
        except CLIValidationError as exception_:
            raise exception_
        project_config = ProjectConfigLoader.load_using_server_config(
            server_config
        )
        run_strictdoc_server(
            server_config=server_config, project_config=project_config
        )
