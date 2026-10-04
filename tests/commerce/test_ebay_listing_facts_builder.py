from src.commerce.ebay_listing_facts_builder import resolve_required_aspects


def test_resolves_required_aspect_from_title():
    taxonomy = [
        {
            "localizedAspectName": "Type",
            "aspectConstraint": {
                "aspectRequired": True
            },
            "aspectValues": [
                {"localizedValue": "Cover"},
                {"localizedValue": "Gig Bag"},
                {"localizedValue": "Hard Case"},
            ],
        }
    ]

    result = resolve_required_aspects(
        title="41 Inch Guitar Gig Bag Water Resistant Case",
        supplier_html="<html></html>",
        taxonomy_aspects=taxonomy,
    )

    assert result["complete"] is True
    assert result["missing"] == []
    assert result["resolved"] == {
        "Type": ["Gig Bag"]
    }


def test_missing_required_aspect_is_not_invented():
    taxonomy = [
        {
            "localizedAspectName": "Brand",
            "aspectConstraint": {
                "aspectRequired": True
            },
            "aspectValues": [
                {"localizedValue": "Unbranded"},
                {"localizedValue": "Yamaha"},
            ],
        }
    ]

    result = resolve_required_aspects(
        title="41 Inch Guitar Gig Bag",
        supplier_html="<html>Water resistant padded case</html>",
        taxonomy_aspects=taxonomy,
    )

    assert result["complete"] is False
    assert result["resolved"] == {}
    assert result["missing"] == ["Brand"]


def test_non_required_aspects_are_ignored():
    taxonomy = [
        {
            "localizedAspectName": "Colour",
            "aspectConstraint": {
                "aspectRequired": False
            },
            "aspectValues": [
                {"localizedValue": "Black"}
            ],
        }
    ]

    result = resolve_required_aspects(
        title="Black Guitar Bag",
        supplier_html="<html></html>",
        taxonomy_aspects=taxonomy,
    )

    assert result["complete"] is True
    assert result["resolved"] == {}
    assert result["missing"] == []


def test_brand_is_not_inferred_from_unlabelled_page_text():
    taxonomy = [
        {
            "localizedAspectName": "Brand",
            "aspectConstraint": {"aspectRequired": True},
            "aspectValues": [
                {"localizedValue": "Unbranded"},
                {"localizedValue": "Access"},
            ],
        }
    ]

    result = resolve_required_aspects(
        title="41 Inch Guitar Bag Water Resistant Case",
        supplier_html="<html>Easy access storage compartment</html>",
        taxonomy_aspects=taxonomy,
    )

    assert result["resolved"] == {}
    assert result["missing"] == ["Brand"]
    assert result["complete"] is False


def test_longest_specific_type_wins():
    taxonomy = [
        {
            "localizedAspectName": "Type",
            "aspectConstraint": {"aspectRequired": True},
            "aspectValues": [
                {"localizedValue": "Cover"},
                {"localizedValue": "Gig Bag"},
                {"localizedValue": "Hard Case"},
            ],
        }
    ]

    result = resolve_required_aspects(
        title="41 Inch Guitar Bag Water Resistant Guitar Case Black Padded Gig Bag",
        supplier_html="<html>Protective cover included</html>",
        taxonomy_aspects=taxonomy,
    )

    assert result["resolved"] == {
        "Type": ["Gig Bag"]
    }
