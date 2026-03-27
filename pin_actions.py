#!/usr/bin/env python3
"""
Script to unify and pin GitHub Actions to specific commit hashes across workflow and action YAML files.
Handles both tag-based references (@v4) and existing hash-based references.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict

# Action mappings: action name -> (commit hash, version comment)
ACTION_PINS = {
    'actions/checkout': ('de0fac2e4500dabe0009e67214ff5f5447ce83dd', 'v6.0.2'),
    'actions/setup-python': ('a309ff8b426b58ec0e2a45f0f869d46889d02405', 'v6.2.0'),
    'actions/setup-node': ('53b83947a5a98c8d113130e565377fae1a50d02f', 'v6.3.0'),
    'actions/upload-artifact': ('bbbca2ddaa5d8feaa63e36b76fdaad77386f024f', 'v7.0.0'),
}


def find_yaml_files(root_dir: str) -> List[Path]:
    """Find all workflow and action YAML files in the repository."""
    yaml_files = []
    
    # Find workflow files
    workflows_dir = Path(root_dir) / '.github' / 'workflows'
    if workflows_dir.exists():
        yaml_files.extend(workflows_dir.glob('*.yaml'))
        yaml_files.extend(workflows_dir.glob('*.yml'))
    
    # Find action files
    actions_dir = Path(root_dir) / '.github' / 'actions'
    if actions_dir.exists():
        yaml_files.extend(actions_dir.glob('**/action.yml'))
        yaml_files.extend(actions_dir.glob('**/action.yaml'))
    
    return sorted(yaml_files)


def collect_existing_references(content: str) -> Dict[str, Set[str]]:
    """
    Collect all existing action references (both tags and hashes) from the content.
    Returns a dict mapping action names to sets of their current references.
    """
    references = {}
    
    for action_name in ACTION_PINS.keys():
        refs = set()
        
        # Pattern to match action with either tag or hash (with optional comment)
        # Matches: actions/checkout@v4, actions/checkout@abc123..., actions/checkout@abc123 # v4.1.0
        pattern = rf'{re.escape(action_name)}@([a-f0-9]+|v\d+(?:\.\d+)?(?:\.\d+)?)(?:\s*#\s*[^\n]*)?'
        
        matches = re.findall(pattern, content)
        if matches:
            refs.update(matches)
            references[action_name] = refs
    
    return references


def update_action_references(content: str) -> Tuple[str, int, Dict[str, Set[str]]]:
    """
    Update action references to use standardized pinned commit hashes.
    Returns updated content, count of replacements made, and dict of what was replaced.
    """
    updated_content = content
    replacement_count = 0
    replacements_made = defaultdict(set)
    
    for action_name, (commit_hash, version) in ACTION_PINS.items():
        # Pattern to match action with either:
        # 1. Version tag: @v4, @v5, etc.
        # 2. Commit hash: @abc123... (40 char hex)
        # 3. Either of above with optional comment
        pattern = rf'({re.escape(action_name)})@([a-f0-9]{{40}}|v\d+(?:\.\d+)?(?:\.\d+)?)(?:\s*#\s*[^\n]*)?'
        
        # Replacement: action@hash # version
        replacement = rf'\1@{commit_hash} # {version}'
        
        # Find all matches to count and track them
        matches = list(re.finditer(pattern, updated_content))
        
        for match in matches:
            ref = match.group(2)  # The version tag or hash
            # Only count if it's not already the target hash
            if ref != commit_hash:
                replacement_count += 1
                replacements_made[action_name].add(ref)
        
        # Perform replacement
        updated_content = re.sub(pattern, replacement, updated_content)
    
    return updated_content, replacement_count, dict(replacements_made)


def process_file(file_path: Path) -> Tuple[bool, int, Dict[str, Set[str]]]:
    """
    Process a single YAML file and update action references.
    Returns (whether file was modified, number of replacements, what was replaced).
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        updated_content, count, replacements = update_action_references(original_content)
        
        if updated_content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            return True, count, replacements
        
        return False, 0, {}
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False, 0, {}


def format_reference(ref: str) -> str:
    """Format a reference for display (truncate hashes, keep tags as-is)."""
    if ref.startswith('v'):
        return ref
    elif len(ref) == 40:  # Full commit hash
        return f"{ref[:8]}..."
    else:
        return ref


def main():
    """Main function to process all YAML files."""
    # Get repository root (parent of script directory)
    repo_root = Path(__file__).parent
    
    print("=" * 80)
    print("GitHub Actions Unification Script")
    print("=" * 80)
    print(f"\nRepository: {repo_root}")
    print(f"\nStandardized action pins:")
    for action, (hash_val, version) in ACTION_PINS.items():
        print(f"  • {action}@{hash_val[:8]}... # {version}")
    print("\n" + "-" * 80)
    
    # Find all YAML files
    yaml_files = find_yaml_files(repo_root)
    
    if not yaml_files:
        print("No workflow or action YAML files found.")
        return
    
    print(f"\nFound {len(yaml_files)} YAML file(s) to process.\n")
    
    # Process each file
    total_files_modified = 0
    total_replacements = 0
    all_replacements = defaultdict(set)
    
    for file_path in yaml_files:
        relative_path = file_path.relative_to(repo_root)
        modified, count, replacements = process_file(file_path)
        
        if modified:
            total_files_modified += 1
            total_replacements += count
            
            # Track all unique replacements made
            for action, refs in replacements.items():
                all_replacements[action].update(refs)
            
            print(f"✓ {relative_path}")
            for action, refs in replacements.items():
                refs_str = ", ".join(f"@{format_reference(r)}" for r in sorted(refs))
                print(f"    └─ {action}: {refs_str} → @{ACTION_PINS[action][0][:8]}... # {ACTION_PINS[action][1]}")
        else:
            print(f"  {relative_path} (no changes)")
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Files processed:    {len(yaml_files)}")
    print(f"Files modified:     {total_files_modified}")
    print(f"Total replacements: {total_replacements}")
    
    if all_replacements:
        print("\nUnified versions:")
        for action in sorted(all_replacements.keys()):
            refs = all_replacements[action]
            target_hash, target_version = ACTION_PINS[action]
            print(f"\n  {action}:")
            print(f"    Found: {', '.join(format_reference(r) for r in sorted(refs))}")
            print(f"    Now:   {target_hash[:8]}... # {target_version}")
    
    print()
    
    if total_files_modified > 0:
        print("✓ All action references have been unified and pinned to standardized versions.")
    else:
        print("✓ All files already use standardized versions - no modifications needed.")


if __name__ == '__main__':
    main()
