import os
from typing import List, Optional

from strictdoc.cli.base_command import CLIValidationError
from strictdoc.helpers.auto_described import auto_described
from strictdoc.helpers.net import is_valid_host


@auto_described
class ServerCommandConfig:
    def __init__(
        self,
        *,
        debug: bool,
        development: bool = False,
        command: str,
        input_path: str,
        output_path: Optional[str],
        config: Optional[str],
        reload: bool,
        host: Optional[str],
        port: Optional[int],
        watch: bool = False,
        auth_proxy_user_header: Optional[str] = None,
        auth_proxy_email_header: Optional[str] = None,
        auth_proxy_name_header: Optional[str] = None,
        auth_proxy_groups_header: Optional[str] = None,
        auth_editor_group: Optional[List[str]] = None,
        auth_admin_group: Optional[List[str]] = None,
    ):
        self.debug: bool = debug
        self.development: bool = development
        self.command: str = command
        self._input_path: str = input_path
        self.output_path: Optional[str] = output_path
        self._config_path: Optional[str] = config
        self.reload: bool = reload
        self.host: Optional[str] = host
        self.port: Optional[int] = port
        self.watch: bool = watch
        self.auth_proxy_user_header: Optional[str] = auth_proxy_user_header
        self.auth_proxy_email_header: Optional[str] = auth_proxy_email_header
        self.auth_proxy_name_header: Optional[str] = auth_proxy_name_header
        self.auth_proxy_groups_header: Optional[str] = auth_proxy_groups_header
        # Singular parameter names: argparse collects repeated
        # --auth-editor-group / --auth-admin-group options into these.
        self.auth_editor_groups: List[str] = (
            auth_editor_group if auth_editor_group is not None else []
        )
        self.auth_admin_groups: List[str] = (
            auth_admin_group if auth_admin_group is not None else []
        )

    def get_full_input_path(self) -> str:
        return os.path.abspath(self._input_path)

    def get_path_to_config(self) -> str:
        return (
            self._config_path
            if self._config_path is not None
            else self._input_path
        )

    def validate(self) -> None:
        if not os.path.exists(self._input_path):
            raise CLIValidationError(
                f"Provided input path does not exist: {self._input_path}"
            )

        if self._config_path is not None and not os.path.exists(
            self._config_path
        ):
            raise CLIValidationError(
                "Provided path to a configuration file does not exist: "
                f"{self._config_path}"
            )

        for header_ in (
            self.auth_proxy_user_header,
            self.auth_proxy_email_header,
            self.auth_proxy_name_header,
            self.auth_proxy_groups_header,
        ):
            if header_ is not None and len(header_.strip()) == 0:
                raise CLIValidationError(
                    "Provided auth proxy header name must not be empty."
                )

        if (
            self.auth_proxy_email_header is not None
            or self.auth_proxy_name_header is not None
        ) and self.auth_proxy_user_header is None:
            raise CLIValidationError(
                "--auth-proxy-email-header and --auth-proxy-name-header "
                "require --auth-proxy-user-header."
            )

        if (
            len(self.auth_editor_groups) > 0 or len(self.auth_admin_groups) > 0
        ) and self.auth_proxy_groups_header is None:
            raise CLIValidationError(
                "--auth-editor-group and --auth-admin-group require "
                "--auth-proxy-groups-header."
            )
        if self.auth_proxy_groups_header is not None and (
            self.auth_proxy_user_header is None
        ):
            raise CLIValidationError(
                "--auth-proxy-groups-header requires --auth-proxy-user-header."
            )
        for group_ in self.auth_editor_groups + self.auth_admin_groups:
            if len(group_.strip()) == 0:
                raise CLIValidationError(
                    "Provided group name must not be empty."
                )

        if (host_ := self.host) is not None:
            if not is_valid_host(host_):
                raise CLIValidationError(
                    f"Provided 'host' argument is not a valid host: {host_}"
                )
