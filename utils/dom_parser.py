from typing import Dict, Any, List, Optional
import json

def prune_accessibility_node(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Recursively prunes the accessibility tree node to retain only interactive elements,
    labeled elements, and essential layout boundaries.
    """
    if not node:
        return None

    # Recursively prune children first
    pruned_children = []
    for child in node.get("children", []):
        pruned_child = prune_accessibility_node(child)
        if pruned_child:
            pruned_children.append(pruned_child)

    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")
    description = node.get("description", "")
    
    # We want to keep all elements that are interactive, or have some textual identifier/value
    interactive_roles = {
        "button", "textbox", "checkbox", "combobox", "listbox", "link",
        "searchbox", "menuitem", "radio", "option", "treeitem", "tab",
        "switch", "spinbutton", "slider", "heading"
    }

    is_interactive = role.lower() in interactive_roles
    has_text_or_val = bool(name or value or description)
    
    # Keep attributes that signal state or requirements
    state_attributes = {}
    for attr in ["checked", "disabled", "expanded", "focused", "modal", "multiline", "multiselectable", "readonly", "required", "selected"]:
        if attr in node:
            state_attributes[attr] = node[attr]

    # If this is a container (e.g. WebArea, group, generic, list) with no info and no children, discard it.
    # Otherwise, if it has valuable information or has children containing valuable information, keep it.
    if is_interactive or has_text_or_val or state_attributes or pruned_children:
        pruned = {
            "role": role,
        }
        if name:
            pruned["name"] = name
        if value:
            pruned["value"] = value
        if description:
            pruned["description"] = description
            
        # Add state attributes
        pruned.update(state_attributes)
        
        # If it's a generic layout container but has children, we keep it but don't pollute with its keys
        if pruned_children:
            pruned["children"] = pruned_children
            
        return pruned

    return None

def flatten_accessibility_tree(node: Dict[str, Any], depth: int = 0) -> List[str]:
    """
    Converts a pruned accessibility tree into a compact, human-readable indented string format
    which works exceptionally well with LLM prompts.
    """
    lines = []
    role = node.get("role", "element")
    name = node.get("name", "")
    value = node.get("value", "")
    description = node.get("description", "")
    
    # Formulate attributes
    attrs = []
    for k, v in node.items():
        if k not in ["role", "name", "value", "description", "children"] and v is not None:
            attrs.append(f"{k}={v}")
    
    attr_str = f" [{', '.join(attrs)}]" if attrs else ""
    val_str = f" value='{value}'" if value else ""
    desc_str = f" description='{description}'" if description else ""
    
    name_part = f" '{name}'" if name else ""
    line = f"{'  ' * depth}<{role}{name_part}{val_str}{desc_str}{attr_str}>"
    lines.append(line)
    
    for child in node.get("children", []):
        lines.extend(flatten_accessibility_tree(child, depth + 1))
        
    return lines

def format_accessibility_tree(snapshot: Dict[str, Any]) -> str:
    """
    Prunes the snapshot and formats it as an indented tree representation.
    """
    pruned = prune_accessibility_node(snapshot)
    if not pruned:
        return "<Empty Accessibility Tree>"
    
    flat_lines = flatten_accessibility_tree(pruned)
    return "\n".join(flat_lines)
