import unittest

from src.photo_pages import DEFAULT_PAGE_ID, PageAssignments


class PageAssignmentsTests(unittest.TestCase):
    def test_default_page_is_locked_and_receives_unassigned_photos(self):
        assignments = PageAssignments()

        default_page = assignments.get_page(DEFAULT_PAGE_ID)
        self.assertIsNotNone(default_page)
        self.assertEqual(default_page.name, "Page 1")
        self.assertTrue(default_page.locked)

        assignments.auto_assign_unassigned(["/photos/a.jpg", "/photos/b.jpg"])

        self.assertEqual(default_page.photo_paths, ["/photos/a.jpg", "/photos/b.jpg"])

    def test_deleting_non_default_page_moves_photos_to_page_one(self):
        assignments = PageAssignments()
        page = assignments.add_page("Roof")
        assignments.assign_photo("/photos/roof-1.jpg", page.id)
        assignments.assign_photo("/photos/roof-2.jpg", page.id)

        removed = assignments.remove_page(page.id)

        self.assertTrue(removed)
        self.assertIsNone(assignments.get_page(page.id))
        self.assertEqual(
            assignments.get_page(DEFAULT_PAGE_ID).photo_paths,
            ["/photos/roof-1.jpg", "/photos/roof-2.jpg"],
        )
        self.assertEqual(
            assignments.get_page_for_photo("/photos/roof-1.jpg").id,
            DEFAULT_PAGE_ID,
        )

    def test_prune_removes_deleted_photos_and_keeps_remaining_assignments(self):
        assignments = PageAssignments()
        page = assignments.add_page("Interior")
        assignments.assign_photo("/photos/a.jpg", page.id)
        assignments.assign_photo("/photos/b.jpg", page.id)
        assignments.assign_photo("/photos/c.jpg", DEFAULT_PAGE_ID)

        assignments.prune_to_photos(["/photos/a.jpg", "/photos/c.jpg"])

        self.assertEqual(page.photo_paths, ["/photos/a.jpg"])
        self.assertEqual(assignments.get_page(DEFAULT_PAGE_ID).photo_paths, ["/photos/c.jpg"])


if __name__ == "__main__":
    unittest.main()
