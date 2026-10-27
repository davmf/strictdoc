"""
Find the project actions that a SysML design element offers on its page.
"""

from dataclasses import dataclass
from typing import List, Optional, Union
from urllib.parse import urlencode

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sysml import node_data
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.project_actions.project_action import ProjectAction


@dataclass
class BoundProjectAction:
    action: ProjectAction
    element_name: str

    def get_url(self) -> str:
        return "/project_actions?" + urlencode(
            {"action": self.action.handle, "element": self.element_name}
        )


def find_bound_project_actions(
    project_config: ProjectConfig, node: Union[SDocDocument, SDocNode]
) -> List[BoundProjectAction]:
    if not project_config.is_activated_project_actions():
        return []
    if not isinstance(node, SDocNode) or not node_data.is_design_element_node(
        node
    ):
        return []
    element_name: Optional[str] = node.reserved_title
    if element_name is None:
        return []
    element_kind = node.get_meta_field_value_by_title("ELEMENT_KIND")
    lineage = node_data.get_type_lineage(node)
    result: List[BoundProjectAction] = []
    for action_ in project_config.project_actions:
        binding = action_.sysml_binding
        if binding is None:
            continue
        if binding.element_kind != element_kind:
            continue
        if binding.specializes not in lineage:
            continue
        result.append(
            BoundProjectAction(action=action_, element_name=element_name)
        )
    return result
