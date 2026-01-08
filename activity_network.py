"""
Activity Network Builder

Builds a hierarchical activity tree from refined keystroke text by:
1. Identifying unique activities (Layer 1) from refined text
2. Aggregating activities into higher-level concepts (Layer 2, 3, etc.)
3. Continuing until reaching a single root node (Day's Activity)

Uses LLM pipeline to identify and aggregate activities recursively.
"""

import os
import re
import json
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import defaultdict

from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


@dataclass
class ActivityNode:
    """Represents a node in the activity tree."""
    id: str
    label: str
    layer: int
    content: str = ""  # Original text content for this activity
    children: List[str] = field(default_factory=list)  # IDs of child nodes
    parent: Optional[str] = None  # ID of parent node


def parse_refined_text(file_path: str) -> List[Dict[str, str]]:
    """
    Parse refined text file to extract activities with timestamps and content.
    
    Format expected:
    [timestamp]
    [app/activity name]
    [content text]
    
    Returns:
        List of dictionaries with 'timestamp', 'activity', and 'content' keys
    """
    activities = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return activities
    except Exception as e:
        print(f"Error reading file: {e}")
        return activities
    
    # Split by timestamp pattern (e.g., "8 Jan 2026 at 12:30 AM")
    # Pattern: day month year at time AM/PM
    timestamp_pattern = r'(\d{1,2}\s+\w+\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s+(?:AM|PM))'
    
    sections = re.split(timestamp_pattern, content)
    
    # Process sections (skip first empty if split starts with pattern)
    i = 1 if sections[0].strip() == '' else 0
    
    while i < len(sections) - 1:
        timestamp = sections[i].strip()
        text_block = sections[i + 1].strip() if i + 1 < len(sections) else ""
        
        if not timestamp or not text_block:
            i += 2
            continue
        
        # Split text block into lines
        lines = [line.strip() for line in text_block.split('\n') if line.strip()]
        
        if not lines:
            i += 2
            continue
        
        # First non-empty line is typically the activity/app name
        activity_name = lines[0]
        # Rest is the content
        activity_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        
        # If no content but activity name exists, use activity name as content
        if not activity_content and activity_name:
            activity_content = activity_name
        
        # Only add if we have a valid activity name
        if activity_name:
            activities.append({
                'timestamp': timestamp,
                'activity': activity_name,
                'content': activity_content
            })
        
        i += 2
    
    return activities


def identify_layer1_activities(activities: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Identify unique Layer 1 activities from parsed activities.
    Groups activities by their app/activity name.
    
    Returns:
        Dictionary mapping activity names to their activity entries
    """
    activity_groups = defaultdict(list)
    
    for activity in activities:
        activity_name = activity['activity'].strip()
        if activity_name:
            activity_groups[activity_name].append(activity)
    
    return dict(activity_groups)


def extract_activity_concepts_llm(activity_name: str, activities: List[Dict[str, str]]) -> List[str]:
    """
    Use LLM to extract high-level concepts from an activity group.
    
    Args:
        activity_name: Name of the activity (e.g., "Code Editor")
        activities: List of activity entries for this activity
        
    Returns:
        List of concept strings (2-4 concepts)
    """
    # Combine all content for this activity
    combined_content = f"Activity: {activity_name}\n\n"
    for act in activities:
        combined_content += f"Timestamp: {act['timestamp']}\n"
        combined_content += f"Content: {act['content']}\n\n"
    
    prompt = f"""Analyze the following activity entries and extract 2-4 high-level concepts or themes that represent this activity.

{combined_content}

Each concept should be a short phrase (2-5 words) that captures the key purpose, theme, or pattern of this activity.

Return ONLY a JSON array of concept strings, nothing else. Example format:
["concept one", "concept two", "concept three"]

If you cannot identify meaningful concepts, return an empty array []."""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_completion_tokens=256,
        )
        
        response = completion.choices[0].message.content.strip()
        
        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            concepts = json.loads(response)
            if isinstance(concepts, list):
                return [str(c).lower().strip() for c in concepts[:4] if c]
        except json.JSONDecodeError:
            pass
        
        # Fallback: split by newlines or commas
        concepts = [c.strip().strip('"\'[]') for c in response.replace('\n', ',').split(',')]
        return [c.lower() for c in concepts if c][:4]
        
    except Exception as e:
        print(f"Error extracting concepts for {activity_name}: {e}")
        # Fallback: use activity name as single concept
        return [activity_name.lower()]


def aggregate_activities_llm(activities: List[str]) -> List[str]:
    """
    Aggregate multiple activities into fewer, broader concepts using LLM.
    
    Args:
        activities: List of activity/concept strings to aggregate
        
    Returns:
        List of broader concept strings (roughly half the input count, minimum 1)
    """
    if len(activities) <= 1:
        return activities
    
    # Target roughly half the activities, minimum 1
    target_count = max(1, len(activities) // 2)
    
    prompt = f"""You are given a list of activities/concepts from someone's daily computer usage.
Your task is to group and merge these into {target_count} broader, higher-level activity concepts.

Activities to aggregate:
{json.dumps(activities, indent=2)}

Merge related activities together into broader themes. Each new concept should be a short phrase (2-6 words) that represents a category or theme.

Return ONLY a JSON array of the {target_count} broader concept strings, nothing else. Example format:
["broader concept one", "broader concept two"]"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_completion_tokens=256,
        )
        
        response = completion.choices[0].message.content.strip()
        
        # Parse JSON response
        try:
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            broader = json.loads(response)
            if isinstance(broader, list):
                return [str(c).lower().strip() for c in broader if c]
        except json.JSONDecodeError:
            pass
        
        # Fallback
        broader = [c.strip().strip('"\'[]') for c in response.replace('\n', ',').split(',')]
        return [c.lower() for c in broader if c][:target_count]
        
    except Exception as e:
        print(f"Error aggregating activities: {e}")
        # Fallback: return first half
        return activities[:target_count] if target_count > 0 else activities


def generate_day_activity_llm(concepts: List[str]) -> str:
    """
    Generate a single day activity concept from the final layer of concepts.
    
    Args:
        concepts: Final layer of concepts to synthesize
        
    Returns:
        Single day activity concept string
    """
    if len(concepts) == 1:
        return concepts[0]
    
    prompt = f"""You are given the final high-level activity concepts from someone's entire day of computer usage.
Synthesize these into ONE single concept that captures the essence of their day's activities.

Final concepts:
{json.dumps(concepts, indent=2)}

Return ONLY a single phrase (3-8 words) that represents the day's overarching activity theme or essence.
Do not include quotes or any other text."""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_completion_tokens=64,
        )
        
        return completion.choices[0].message.content.strip().strip('"\'').lower()
        
    except Exception as e:
        print(f"Error generating day activity: {e}")
        # Fallback: combine concepts
        return " / ".join(concepts)


def build_activity_tree(file_path: str) -> Dict[str, ActivityNode]:
    """
    Build hierarchical activity tree from refined text file.
    
    Args:
        file_path: Path to refined text file
        
    Returns:
        Dictionary mapping node IDs to ActivityNode objects
    """
    print("=" * 60)
    print("Building Activity Network Tree")
    print("=" * 60)
    
    # Step 1: Parse refined text
    print("\n[Step 1] Parsing refined text file...")
    activities = parse_refined_text(file_path)
    print(f"Found {len(activities)} activity entries")
    
    if not activities:
        print("No activities found. Exiting.")
        return {}
    
    # Step 2: Identify Layer 1 activities (unique app/activity names)
    print("\n[Step 2] Identifying Layer 1 activities...")
    activity_groups = identify_layer1_activities(activities)
    layer1_activities = list(activity_groups.keys())
    print(f"Found {len(layer1_activities)} unique activities: {layer1_activities}")
    
    # Initialize nodes dictionary
    nodes: Dict[str, ActivityNode] = {}
    
    # Step 3: Extract concepts for each Layer 1 activity
    print("\n[Step 3] Extracting concepts for Layer 1 activities...")
    layer1_concepts = {}  # activity_name -> list of concepts
    concept_to_activity = {}  # concept -> activity_name
    
    for activity_name, activity_list in activity_groups.items():
        print(f"  Processing: {activity_name}")
        concepts = extract_activity_concepts_llm(activity_name, activity_list)
        print(f"    → Concepts: {concepts}")
        
        # Create Layer 1 activity nodes
        activity_id = f"L1_{activity_name.replace(' ', '_').replace('/', '_')}"
        combined_content = "\n\n".join([f"{a['timestamp']}\n{a['content']}" for a in activity_list])
        
        nodes[activity_id] = ActivityNode(
            id=activity_id,
            label=activity_name,
            layer=1,
            content=combined_content,
            children=[]
        )
        
        # Create concept nodes for this activity
        # Note: An activity can have multiple concepts, so we set parent to the first one
        # but all relationships are captured via children arrays in concept nodes
        for idx, concept in enumerate(concepts):
            concept_id = f"L2_{concept.replace(' ', '_').replace('/', '_')}"
            if concept_id not in nodes:
                nodes[concept_id] = ActivityNode(
                    id=concept_id,
                    label=concept,
                    layer=2,
                    content="",
                    children=[activity_id],
                    parent=None
                )
                concept_to_activity[concept] = activity_name
            else:
                # Concept already exists (shared by multiple activities), add this activity as child
                if activity_id not in nodes[concept_id].children:
                    nodes[concept_id].children.append(activity_id)
            
            # Set parent for activity node (only set once, to first concept)
            # All relationships are properly captured via children arrays above
            if idx == 0:
                nodes[activity_id].parent = concept_id
        
        layer1_concepts[activity_name] = concepts
    
    # Step 4: Recursive aggregation
    print("\n[Step 4] Aggregating concepts into higher layers...")
    current_layer = 2
    current_concepts = list(set([c for concepts in layer1_concepts.values() for c in concepts]))
    current_concept_ids = [f"L2_{c.replace(' ', '_').replace('/', '_')}" for c in current_concepts]
    
    while len(current_concepts) > 1:
        current_layer += 1
        print(f"\n  Aggregating to Layer {current_layer}...")
        print(f"    Current concepts ({len(current_concepts)}): {current_concepts[:5]}{'...' if len(current_concepts) > 5 else ''}")
        
        # Aggregate concepts
        broader_concepts = aggregate_activities_llm(current_concepts)
        print(f"    → Aggregated to {len(broader_concepts)}: {broader_concepts}")
        
        # If aggregation didn't reduce, force reduction or break
        if len(broader_concepts) >= len(current_concepts):
            if len(current_concepts) <= 2:
                # Generate final day concept
                break
            broader_concepts = broader_concepts[:len(current_concepts)//2]
        
        # Map current concepts to broader concepts using LLM
        concept_mapping: Dict[str, List[str]] = {bc: [] for bc in broader_concepts}
        
        # Use LLM to intelligently map concepts to broader categories
        mapping_prompt = f"""You are given a list of activity concepts and a list of broader categories.
Map each concept to the most appropriate broader category.

Concepts to map:
{json.dumps(current_concepts, indent=2)}

Broader categories:
{json.dumps(broader_concepts, indent=2)}

Return ONLY a JSON object mapping each concept to a broader category. Format:
{{"concept1": "broader_category1", "concept2": "broader_category2", ...}}

Each concept should be mapped to exactly one broader category."""
        
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": mapping_prompt}],
                temperature=0.3,
                max_completion_tokens=512,
            )
            
            response = completion.choices[0].message.content.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            mapping = json.loads(response)
            
            # Apply mapping
            for i, concept in enumerate(current_concepts):
                broader = mapping.get(concept.lower(), broader_concepts[i % len(broader_concepts)])
                if broader in broader_concepts:
                    concept_mapping[broader].append(current_concept_ids[i])
                else:
                    # Fallback to round-robin if mapping is invalid
                    concept_mapping[broader_concepts[i % len(broader_concepts)]].append(current_concept_ids[i])
        except Exception as e:
            print(f"    Warning: LLM mapping failed ({e}), using round-robin assignment")
            # Fallback to round-robin
            for i, concept in enumerate(current_concepts):
                broader_idx = i % len(broader_concepts)
                concept_mapping[broader_concepts[broader_idx]].append(current_concept_ids[i])
        
        # Create new layer nodes
        new_concept_ids = []
        for broader in broader_concepts:
            concept_id = f"L{current_layer}_{broader.replace(' ', '_').replace('/', '_')}"
            children = concept_mapping.get(broader, [])
            
            nodes[concept_id] = ActivityNode(
                id=concept_id,
                label=broader,
                layer=current_layer,
                content="",
                children=children,
                parent=None
            )
            new_concept_ids.append(concept_id)
            
            # Update parent references for children
            for child_id in children:
                if child_id in nodes:
                    nodes[child_id].parent = concept_id
        
        current_concepts = broader_concepts
        current_concept_ids = new_concept_ids
    
    # Step 5: Generate final day activity
    print("\n[Step 5] Generating final day activity...")
    day_activity = generate_day_activity_llm(current_concepts)
    print(f"  → Day's Activity: {day_activity}")
    
    day_activity_id = "day_activity"
    nodes[day_activity_id] = ActivityNode(
        id=day_activity_id,
        label=day_activity,
        layer=current_layer + 1,
        content="",
        children=current_concept_ids,
        parent=None
    )
    
    # Update parent references
    for concept_id in current_concept_ids:
        if concept_id in nodes:
            nodes[concept_id].parent = day_activity_id
    
    print("\n" + "=" * 60)
    print("Activity Tree Built Successfully!")
    print("=" * 60)
    
    return nodes


def print_tree_summary(nodes: Dict[str, ActivityNode]):
    """Print a summary of the activity tree."""
    if not nodes:
        print("No nodes to display.")
        return
    
    # Group nodes by layer
    layers = {}
    for node in nodes.values():
        if node.layer not in layers:
            layers[node.layer] = []
        layers[node.layer].append(node)
    
    print("\n" + "=" * 60)
    print("TREE SUMMARY")
    print("=" * 60)
    
    for layer in sorted(layers.keys()):
        layer_nodes = layers[layer]
        if layer == 1:
            print(f"\nLayer {layer} (Activities): {len(layer_nodes)} nodes")
            for n in layer_nodes:
                print(f"  • {n.label}")
        elif layer_nodes[0].id == "day_activity":
            print(f"\nLayer {layer} (Day's Activity):")
            print(f"  → {layer_nodes[0].label}")
        else:
            print(f"\nLayer {layer} (Concepts): {len(layer_nodes)} nodes")
            for n in layer_nodes:
                print(f"  • {n.label}")


def tree_to_dict(nodes: Dict[str, ActivityNode], truncate_content: bool = True) -> Dict:
    """
    Convert activity tree nodes to a JSON-serializable dictionary.
    
    Args:
        nodes: Dictionary of ActivityNode objects
        truncate_content: If True, truncate content to 200 chars for display
        
    Returns:
        Dictionary with 'nodes' list containing serialized node data
    """
    tree_data = {
        'nodes': [
            {
                'id': node.id,
                'label': node.label,
                'layer': node.layer,
                'content': (node.content[:200] + "..." if len(node.content) > 200 else node.content) if truncate_content else node.content,
                'children': node.children,
                'parent': node.parent
            }
            for node in nodes.values()
        ]
    }
    return tree_data


def save_tree_json(nodes: Dict[str, ActivityNode], output_path: str):
    """Save the activity tree to a JSON file."""
    tree_data = tree_to_dict(nodes, truncate_content=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tree_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nTree saved to: {output_path}")


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python activity_network.py <path_to_refined_text_file>")
        print("Example: python activity_network.py data/2026-01-08_refined.txt")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    # Build the activity tree
    nodes = build_activity_tree(file_path)
    
    if not nodes:
        print("Failed to build activity tree.")
        sys.exit(1)
    
    # Print summary
    print_tree_summary(nodes)
    
    # Save to JSON
    output_path = file_path.replace('.txt', '_tree.json')
    save_tree_json(nodes, output_path)
    
    print("\nDone!")


if __name__ == "__main__":
    main()

