import json

import pytest

from omr_studio.services.templates import TemplateError


def test_import_flattens_and_lists(library, samples):
    info = library.import_template(samples / "sample1", "Sample One")
    assert info.name == "Sample One" and info.id == "sample-one"
    assert (info.path / "template.json").is_file() and (info.path / "omr_marker.jpg").is_file()
    assert not any(p.is_dir() for p in info.path.iterdir())          # flat: no nested batches
    assert [t.id for t in library.list()] == ["sample-one"]


def test_duplicate_names_get_unique_ids(library, samples):
    a = library.import_template(samples / "sample1", "Same")
    b = library.import_template(samples / "sample1", "Same")
    assert a.id != b.id


def test_answer_key_roundtrip(library, samples):
    info = library.import_template(samples / "sample1", "Plain")
    assert not info.has_answer_key
    keyed = library.import_template(samples / "answer-key" / "using-csv", "Keyed")
    assert keyed.has_answer_key and keyed.question_count == 5
    assert not library.remove_answer_key(keyed.id).has_answer_key


def test_invalid_json_rejected_without_residue(library, tmp_path):
    bad = tmp_path / "template.json"
    bad.write_text("{ nope")
    with pytest.raises(TemplateError, match="not valid JSON"):
        library.import_template(bad)
    assert library.list() == []


def test_missing_marker_rejected(library, tmp_path, samples):
    src = json.loads((samples / "sample1" / "template.json").read_text())
    (tmp_path / "template.json").write_text(json.dumps(src))          # marker image not copied alongside
    with pytest.raises(TemplateError, match="not found"):
        library.import_template(tmp_path)


def test_remove(library, samples):
    info = library.import_template(samples / "sample1", "Gone")
    library.remove(info.id)
    assert library.list() == []
