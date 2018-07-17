import pytest
import marshmallow as ma

from flask_vgavro_utils.schemas import NestedFromValue


@pytest.mark.parametrize("same_schema_instance", [True, False])
def test_nested_from_value(same_schema_instance):
    class TypeXDataSchema(ma.Schema):
        x = ma.fields.Str(required=True)

    class TypeYDataSchema(ma.Schema):
        y = ma.fields.Str(required=True)

    class MySchema(ma.Schema):
        class Meta:
            strict = True

        TYPE_DATA_SCHEMA_MAP = {
            'type-x': TypeXDataSchema,
            'type-y': TypeYDataSchema,
        }
        type = ma.fields.Str()
        data = NestedFromValue('type', TYPE_DATA_SCHEMA_MAP)

    if same_schema_instance:
        _schema = MySchema()
        schema = lambda: _schema  # noqa
    else:
        schema = MySchema

    assert schema().load({"type": "type-x", "data": {"x": "123"}})
    assert schema().load({"type": "type-y", "data": {"y": "123"}})

    with pytest.raises(ma.ValidationError) as exc:
        schema().load({"type": "type-y", "data": {"x": "123"}})
    assert exc.value.messages == {'data': {'y': ['Missing data for required field.']}}

    with pytest.raises(ma.ValidationError) as exc:
        schema().load({"type": "type-x", "data": {"y": "123"}})
    assert exc.value.messages == {'data': {'x': ['Missing data for required field.']}}

    assert 'x' in schema().dump({'type': 'type-x', 'data': {'x': 123}})['data']
    assert 'x' not in schema().dump({'type': 'type-y', 'data': {'x': 123}})['data']
