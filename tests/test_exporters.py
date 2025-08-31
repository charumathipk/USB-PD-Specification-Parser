import tempfile, os, json
from usb_pd_parser.exporters.export_json import export_to_json
from usb_pd_parser.exporters.export_excel import export_to_excel


def test_export_json():
    data = [{
        'section_id': '1',
        'title': 'Introduction',
        'content': 'This is test content',
        'doc_title': 'DummyDoc',
        'full_path': '1 Introduction',
        'page': 1,
        'level': 1,
        'parent_id': None,
        'tags': []
    }]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
    tmp.close()
    export_to_json(data, tmp.name)
    with open(tmp.name, 'r', encoding='utf-8') as f:
        j = json.load(f)
    assert isinstance(j, list)
    assert j[0]['title'] == 'Introduction'
    os.remove(tmp.name)


def test_export_excel():
    data = [{
        'section_id': '1',
        'title': 'Introduction',
        'content': 'This is test content',
        'doc_title': 'DummyDoc',
        'full_path': '1 Introduction',
        'page': 1,
        'level': 1,
        'parent_id': None,
        'tags': []
    }]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    export_to_excel(data, tmp.name)
    assert os.path.exists(tmp.name)
    os.remove(tmp.name)
