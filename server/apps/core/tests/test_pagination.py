from django.core.paginator import Paginator
from django.test import SimpleTestCase

from apps.core.pagination import (
    DEFAULT_PER_PAGE,
    PER_PAGE_CHOICES,
    get_elided_page_numbers,
    parse_per_page,
)
from apps.core.templatetags.pagination_tags import elided_pages


class PaginationHelpersTestCase(SimpleTestCase):
    def test_default_constants(self):
        self.assertEqual(DEFAULT_PER_PAGE, 10)
        self.assertEqual(PER_PAGE_CHOICES, (10, 15, 20, 25))

    def test_parse_per_page_valid(self):
        for choice in (10, 15, 20, 25):
            self.assertEqual(parse_per_page(choice), choice)
            self.assertEqual(parse_per_page(str(choice)), choice)

    def test_parse_per_page_fallback(self):
        self.assertEqual(parse_per_page(None), 10)
        self.assertEqual(parse_per_page(""), 10)
        self.assertEqual(parse_per_page("invalid"), 10)
        self.assertEqual(parse_per_page(0), 10)
        self.assertEqual(parse_per_page(5), 10)
        self.assertEqual(parse_per_page(50), 10)
        self.assertEqual(parse_per_page(-10), 10)

    def test_get_elided_page_numbers_small(self):
        self.assertEqual(get_elided_page_numbers(1, 0), [])
        self.assertEqual(get_elided_page_numbers(1, 1), [1])
        self.assertEqual(get_elided_page_numbers(1, 3), [1, 2, 3])
        self.assertEqual(get_elided_page_numbers(2, 5), [1, 2, 3, 4, 5])

    def test_get_elided_page_numbers_large_first_pages(self):
        res1 = get_elided_page_numbers(1, 72)
        self.assertEqual(res1, [1, 2, 3, 4, "…", 72])
        clickables1 = [x for x in res1 if isinstance(x, int)]
        self.assertEqual(len(clickables1), 5)

        res3 = get_elided_page_numbers(3, 72)
        self.assertEqual(res3, [1, 2, 3, 4, "…", 72])
        self.assertEqual(len([x for x in res3 if isinstance(x, int)]), 5)

    def test_get_elided_page_numbers_middle_pages(self):
        res4 = get_elided_page_numbers(4, 72)
        self.assertEqual(res4, [1, "…", 3, 4, 5, "…", 72])
        clickables4 = [x for x in res4 if isinstance(x, int)]
        self.assertEqual(len(clickables4), 5)
        self.assertEqual(clickables4, [1, 3, 4, 5, 72])

        res35 = get_elided_page_numbers(35, 72)
        self.assertEqual(res35, [1, "…", 34, 35, 36, "…", 72])
        self.assertEqual(len([x for x in res35 if isinstance(x, int)]), 5)

    def test_get_elided_page_numbers_last_pages(self):
        res70 = get_elided_page_numbers(70, 72)
        self.assertEqual(res70, [1, "…", 69, 70, 71, 72])
        self.assertEqual(len([x for x in res70 if isinstance(x, int)]), 5)

        res72 = get_elided_page_numbers(72, 72)
        self.assertEqual(res72, [1, "…", 69, 70, 71, 72])
        self.assertEqual(len([x for x in res72 if isinstance(x, int)]), 5)

    def test_get_elided_page_numbers_always_max_5_clickables(self):
        for total in (6, 7, 10, 72):
            for curr in range(1, total + 1):
                res = get_elided_page_numbers(curr, total)
                clickables = [x for x in res if isinstance(x, int)]
                self.assertEqual(
                    len(clickables), 5,
                    f"Expected 5 clickables for total={total}, curr={curr}, got {clickables}"
                )
                self.assertEqual(clickables[0], 1)
                self.assertEqual(clickables[-1], total)

    def test_elided_pages_template_tag(self):
        paginator = Paginator(range(720), 10)  # 72 pages
        page_obj = paginator.page(4)
        result = elided_pages(page_obj)
        self.assertEqual(result, [1, "…", 3, 4, 5, "…", 72])
        self.assertEqual(elided_pages(None), [])

    def test_elided_pages_template_tag_empty(self):
        paginator = Paginator([], 10)
        page_obj = paginator.page(1)
        self.assertEqual(elided_pages(page_obj), [])
