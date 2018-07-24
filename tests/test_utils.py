from flask_vgavro_utils.app import _convert_int_keys_to_str


def test_convert_int_keys_to_str():
    data = {'key': [{0: '123'}]}
    _convert_int_keys_to_str(data)
    assert data == {'key': [{'0': '123'}]}

    data = {0: 123, '1': 3}
    _convert_int_keys_to_str(data)
    assert data == {'0': 123, '1': 3}
