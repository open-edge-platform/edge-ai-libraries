import os
import tempfile
import unittest

from bounding_box import extract_rectangles_with_labels, parse_numeric


class TestBoundingBox(unittest.TestCase):

    def test_extract_rectangles_with_labels(self):
        svg_content = """<?xml version="1.0"?>
        <svg height="500" width="500" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="20" width="100" height="50" />
            <text x="20" y="40">Label 1</text>
            <rect x="200" y="100" width="80" height="40" />
            <text x="210" y="110">Label 2</text>
            <rect x="300" y="300" width="50" height="50" />
            <!-- No label for this rectangle -->
        </svg>
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as f:
            f.write(svg_content.encode())
            f.close()
            boxes = extract_rectangles_with_labels(f.name)
            os.unlink(f.name)

        # There should be 3 rectangles
        self.assertEqual(len(boxes), 3)
        # First rectangle should have "Label 1"
        self.assertEqual(boxes[0][4], "Label 1")
        # Second rectangle should have "Label 2"
        self.assertEqual(boxes[1][4], "Label 2")
        # Third rectangle should be "Unnamed Rectangle"
        self.assertEqual(boxes[2][4], "Unnamed Rectangle")
        # Check coordinates for the first rectangle
        self.assertEqual(boxes[0][:4], (10, 20, 110, 70))

    def test_percentage_and_missing_values(self):
        svg_content = """<svg xmlns="http://www.w3.org/2000/svg">
            <rect x="10%" y="20%" width="10%" height="10%" />
            <text x="50" y="110">Percent Label</text>
            <rect width="50" height="50" />
        </svg>
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as f:
            f.write(svg_content.encode())
            f.close()
            boxes = extract_rectangles_with_labels(f.name)
            os.unlink(f.name)
        # First rectangle: x=50, y=100, width=50, height=50 (since 10% of 500 is 50)
        self.assertEqual(boxes[0][:4], (50, 100, 100, 150))
        # Second rectangle: missing x/y defaults to 0
        self.assertEqual(boxes[1][:4], (0, 0, 50, 50))

    def test_parse_numeric(self):
        # Test normal numeric values
        self.assertEqual(parse_numeric("100"), 100)
        self.assertEqual(parse_numeric("50.5"), 50)

        # Test percentage values
        self.assertEqual(parse_numeric("50%"), 250)


if __name__ == "__main__":
    unittest.main()
