import random
from test.db_config import DBConfig

import numpy as np
import pytest

from superduper import Document
from superduper.backends.ibis.field_types import dtype
from superduper.backends.mongodb.query import MongoQuery
from superduper.base.constant import KEY_BLOBS
from superduper.components.listener import Listener
from superduper.components.model import ObjectModel
from superduper.components.schema import Schema
from superduper.components.table import Table


def test_listener_serializes_properly():
    q = MongoQuery(table='test').find({}, {})
    listener = Listener(
        model=ObjectModel("test", object=lambda x: x),
        select=q,
        key="test",
    )
    r = listener.encode()

    # check that the result is JSON-able
    import json

    r.pop(KEY_BLOBS)
    print(json.dumps(r, indent=2))


@pytest.mark.parametrize("db", [DBConfig.mongodb_empty], indirect=True)
def test_listener_chaining(db):
    collection = MongoQuery(table='test', db=db)
    data = []

    def insert_random():
        for _ in range(5):
            y = int(random.random() > 0.5)
            x = int(random.random() > 0.5)
            data.append(
                Document(
                    {
                        "x": x,
                        "y": y,
                    }
                )
            )

        db.execute(collection.insert_many(data))

    # Insert data
    insert_random()

    m1 = ObjectModel("m1", object=lambda x: x + 1)
    m2 = ObjectModel("m2", object=lambda x: x + 2)

    listener1 = Listener(
        model=m1,
        select=collection.find({}),
        key="x",
        identifier="listener1",
    )

    listener2 = Listener(
        model=m2,
        select=MongoQuery(table=listener1.outputs).find(),
        key=listener1.outputs,
        identifier='listener2',
    )

    db.add(listener1)
    db.add(listener2)

    docs = list(db.execute(MongoQuery(table=listener1.outputs).find({})))

    assert all([listener1.predict_id in r["_outputs"] for r in docs])

    insert_random()

    docs = list(db.execute(MongoQuery(table=listener2.outputs).find({})))

    assert all([listener2.predict_id in d["_outputs"] for d in docs])


@pytest.mark.parametrize(
    "data",
    [
        1,
        "1",
        {"x": 1},
        [1],
        {
            "x": np.array([1]),
        },
        np.array([[1, 2, 3], [4, 5, 6]]),
    ],
)
@pytest.mark.parametrize("flatten", [False, True])
@pytest.mark.parametrize("db", [DBConfig.mongodb_empty], indirect=True)
def test_create_output_dest_mongodb(db, data, flatten):
    db.cfg.auto_schema = True
    collection = db["test"]

    m1 = ObjectModel(
        "m1",
        object=lambda x: data if not flatten else [data] * 10,
        flatten=flatten,
    )
    q = collection.insert_one(Document({"x": 1}))

    db.execute(q)

    listener1 = Listener(
        model=m1,
        select=collection.find({}),
        key="x",
        identifier="listener1",
    )

    db.add(listener1)

    doc = list(db.execute(listener1.outputs_select))[0]
    result = Document(doc.unpack())[listener1.outputs]
    assert isinstance(result, type(data))
    if isinstance(data, np.ndarray):
        assert np.allclose(result, data)
    else:
        assert result == data


@pytest.mark.parametrize(
    "data",
    [
        1,
        "1",
        {"x": 1},
        [1],
        {
            "x": np.array([1]),
        },
        np.array([[1, 2, 3], [4, 5, 6]]),
    ],
)
@pytest.mark.parametrize("flatten", [True, False])
@pytest.mark.parametrize("db", [DBConfig.sqldb_empty], indirect=True)
def test_create_output_dest_ibis(db, data, flatten):
    db.cfg.auto_schema = True
    schema = Schema(
        identifier="test",
        fields={"x": dtype(int), "id": dtype(str)},
    )
    table = Table("test", schema=schema)
    db.apply(table)

    m1 = ObjectModel(
        "m1",
        object=lambda x: data if not flatten else [data] * 10,
        flatten=flatten,
    )
    db.execute(db['test'].insert([Document({"x": 1, "id": "1"})]))

    listener1 = Listener(
        model=m1,
        select=db['test'].select("x", "id"),
        key="x",
        identifier="listener1",
    )

    db.add(listener1)
    doc = list(db.execute(listener1.outputs_select))[0]
    result = doc[listener1.outputs_key]
    if isinstance(data, np.ndarray):
        assert np.allclose(result, data)
    else:
        assert result == data


@pytest.mark.parametrize(
    "data",
    [
        1,
        "1",
        {"x": 1},
        [1],
        {
            "x": np.array([1]),
        },
        np.array([[1, 2, 3], [4, 5, 6]]),
    ],
)
@pytest.mark.parametrize("db", [DBConfig.mongodb_empty], indirect=True)
def test_listener_cleanup(db, data):
    db.cfg.auto_schema = True
    collection = db["test"]

    m1 = ObjectModel(
        "m1",
        object=lambda x: data,
    )
    q = collection.insert_one(Document({"x": 1}))

    db.execute(q)

    listener1 = Listener(
        model=m1,
        select=collection.find({}),
        key="x",
        identifier="listener1",
    )

    db.add(listener1)
    doc = list(db.execute(listener1.outputs_select))[0]
    result = Document(doc.unpack())[listener1.outputs]
    assert isinstance(result, type(data))
    if isinstance(data, np.ndarray):
        assert np.allclose(result, data)
    else:
        assert result == data

    db.remove('listener', listener1.identifier, force=True)
    assert not db.databackend.check_output_dest(listener1.predict_id)


@pytest.mark.parametrize(
    "data",
    [
        1,
        "1",
        {"x": 1},
        [1],
        {
            "x": np.array([1]),
        },
        np.array([[1, 2, 3], [4, 5, 6]]),
    ],
)
@pytest.mark.parametrize("flatten", [True, False])
@pytest.mark.parametrize("db", [DBConfig.sqldb_empty], indirect=True)
def test_listener_cleanup_ibis(db, data, flatten):
    db.cfg.auto_schema = True
    schema = Schema(
        identifier="test",
        fields={"x": dtype(int), "id": dtype(str)},
    )
    table = Table("test", schema=schema)
    db.apply(table)

    m1 = ObjectModel(
        "m1",
        object=lambda x: data if not flatten else [data] * 10,
        flatten=flatten,
    )
    db.execute(db['test'].insert([Document({"x": 1, "id": "1"})]))

    listener1 = Listener(
        model=m1,
        select=db['test'].select("x", "id"),
        key="x",
        identifier="listener1",
    )

    db.add(listener1)
    db.remove('listener', listener1.identifier, force=True)

    assert listener1.outputs not in db.databackend.conn.tables
