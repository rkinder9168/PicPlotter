import io
import unittest

from PIL import Image

from src.coordinate_transform import PixelPoint
from src.html_map_generator import HTMLMapGenerator


def png_bytes(color):
    image = Image.new("RGB", (8, 8), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def jpg_bytes(color):
    image = Image.new("RGB", (8, 8), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class MultiPageHTMLGeneratorTests(unittest.TestCase):
    def test_multi_page_output_contains_page_navigation_and_scoped_legends(self):
        generator = HTMLMapGenerator(project_name="Page Mode Test", marker_size=64)

        html = generator.generate_multi_page_html(
            [
                {
                    "id": "page-1",
                    "name": "Page 1",
                    "aerial_image_bytes": png_bytes((255, 255, 255)),
                    "aerial_image_mime": "image/png",
                    "aerial_image_size": (8, 8),
                    "photos": [
                        {
                            "filepath": "/photos/a.jpg",
                            "filename": "a.jpg",
                            "display_name": "Front door",
                            "image_data": jpg_bytes((255, 0, 0)),
                        }
                    ],
                    "marker_pixels": [PixelPoint(2, 3)],
                },
                {
                    "id": "page-2",
                    "name": "Interior",
                    "aerial_image_bytes": png_bytes((0, 0, 0)),
                    "aerial_image_mime": "image/png",
                    "aerial_image_size": (8, 8),
                    "photos": [
                        {
                            "filepath": "/photos/b.jpg",
                            "filename": "b.jpg",
                            "display_name": "Kitchen",
                            "image_data": jpg_bytes((0, 255, 0)),
                        }
                    ],
                    "marker_pixels": [PixelPoint(5, 6)],
                },
            ],
            return_content=True,
        )

        self.assertIn("const pageData = ", html)
        self.assertIn('"name": "Interior"', html)
        self.assertIn("page-nav", html)
        self.assertIn("renderLegend", html)
        self.assertIn("Front door", html)
        self.assertIn("Kitchen", html)

    def test_multi_page_output_uses_plain_marker_not_group_color_classes(self):
        generator = HTMLMapGenerator(project_name="Plain Marker Test", marker_size=64)

        html = generator.generate_multi_page_html(
            [
                {
                    "id": "page-1",
                    "name": "Page 1",
                    "aerial_image_bytes": png_bytes((255, 255, 255)),
                    "aerial_image_mime": "image/png",
                    "aerial_image_size": (8, 8),
                    "photos": [
                        {
                            "filepath": "/photos/a.jpg",
                            "filename": "a.jpg",
                            "image_data": jpg_bytes((255, 0, 0)),
                        }
                    ],
                    "marker_pixels": [PixelPoint(2, 3)],
                }
            ],
            return_content=True,
        )

        self.assertIn("--plain-marker-image", html)
        self.assertNotIn("marker-color-", html)
        self.assertNotIn("legend-item", html)


if __name__ == "__main__":
    unittest.main()
