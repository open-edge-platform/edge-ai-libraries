import os
import sys
import xml.etree.ElementTree as ET


def parse_numeric(value, default=0):
    """Convert an SVG value to a number, handling percentages and missing values."""
    if value is None:
        return default
    if "%" in value:  # Handle percentage values (assuming a 500x500 canvas for scaling)
        return int(
            float(value.strip("%")) * 5
        )  # Example: Convert 50% → 250 (assuming 500px width/height)
    try:
        return int(float(value))  # Convert normal numerical values
    except ValueError:
        return default  # Return default if conversion fails


def extract_rectangles_with_labels(svg_file):
    # nosemgrep: use-defused-xml-parse
    tree = ET.parse(svg_file)
    root = tree.getroot()

    rectangles = []
    texts = []

    # Extract all <text> elements with positions
    for elem in root.iter():
        if elem.tag.endswith("text"):
            x = parse_numeric(elem.attrib.get("x"))
            y = parse_numeric(elem.attrib.get("y"))
            text_content = "".join(elem.itertext()).strip()  # Get text inside <text>
            texts.append((x, y, text_content))

    # Extract all <rect> elements
    for elem in root.iter():
        if elem.tag.endswith("rect"):
            x_min = parse_numeric(elem.attrib.get("x"))
            y_min = parse_numeric(elem.attrib.get("y"))
            width = parse_numeric(elem.attrib.get("width"))
            height = parse_numeric(elem.attrib.get("height"))
            x_max, y_max = x_min + width, y_min + height

            # Find the closest text label (inside or above the rect)
            label = "Unnamed Rectangle"
            for text_x, text_y, text_label in texts:
                if x_min <= text_x <= x_max and y_min - 20 <= text_y <= y_max:
                    label = text_label
                    break

            rectangles.append((x_min, y_min, x_max, y_max, label))

    return rectangles


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bounding_box.py <svg_file>")
        sys.exit(1)
    svg_file = sys.argv[1]

    # Create a global path from a relative path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Get rectangles
    rectangles = extract_rectangles_with_labels(os.path.join(BASE_DIR, svg_file))

    # Print the extracted rectangles with labels
    for rect in rectangles:
        print(f"Rectangle: {rect[:4]}, Label: {rect[4]}")
