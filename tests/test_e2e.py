import os
from time import sleep

import elasticsearch
import psycopg
import pytest

from sinker.es import get_client
from sinker.runner import Runner


@pytest.fixture(scope="function")
def wait_for_pg_es():
    """Wait for Postgres and Elasticsearch to become responsive"""
    with open(os.path.join(os.getcwd(), "tests", "fixtures", "schema.sql")) as f:
        ddl_list = f.read()
        while True:
            try:
                psycopg.connect(autocommit=True).execute(ddl_list)
                break
            except psycopg.OperationalError:
                print("Need a database to connect to...")
                sleep(1)
    get_client().cluster.health(wait_for_status="green")


def test_end_to_end(wait_for_pg_es):
    runner = Runner()
    es = get_client()
    # Verify the initial data made it into Elasticsearch
    doc = es.get(index="people", id="p-1")
    assert doc["_source"]["name"] == "John"
    doc = es.get(index="courses", id="c-1")
    expected = {
        "name": "Reth",
        "description": "How to build a modern Ethereum node",
        "teacher": {
            "salary": 100000.0,
            "person": {
                "name": "Prof Georgios"
            }
        },
        "enrollments": [
            {
                "grade": 3.5,
                "student": {
                    "gpa": 3.01,
                    "person": {
                        "name": "John"
                    }
                }
            },
            {
                "grade": 3.14,
                "student": {
                    "gpa": 3.99,
                    "person": {
                        "name": "Loren"
                    }
                }
            }
        ]
    }
    assert doc["_source"] == expected

    # Update a record in Postgres
    psycopg.connect(autocommit=True).execute("update public.person set name = 'Jane' where id = 'p-1'")
    runner.iterate()
    # Verify the update made it into the people index
    doc = es.get(index="people", id="p-1")
    assert doc["_source"]["name"] == "Jane"
    # Verify the update made it into the courses index through person->student->enrollment->course.
    doc = es.get(index="courses", id="c-1")
    expected = {
        "name": "Reth",
        "description": "How to build a modern Ethereum node",
        "teacher": {
            "salary": 100000.0,
            "person": {
                "name": "Prof Georgios"
            }
        },
        "enrollments": [
            {
                "grade": 3.5,
                "student": {
                    "gpa": 3.01,
                    "person": {
                        "name": "Jane"
                    }
                }
            },
            {
                "grade": 3.14,
                "student": {
                    "gpa": 3.99,
                    "person": {
                        "name": "Loren"
                    }
                }
            }
        ]
    }
    assert doc["_source"] == expected

    # Delete the data in Postgres
    psycopg.connect(autocommit=True).execute("delete from public.person where id = 'p-1'")
    runner.iterate()
    # Verify the doc got deleted from Elasticsearch
    with pytest.raises(elasticsearch.NotFoundError):
        es.get(index="people", id="p-1")
    # Verify the doc got deleted from Elasticsearch through person->student->enrollment->course.
    doc = es.get(index="courses", id="c-1")
    expected = {
        "name": "Reth",
        "description": "How to build a modern Ethereum node",
        "teacher": {
            "salary": 100000.0,
            "person": {
                "name": "Prof Georgios"
            }
        },
        "enrollments": [
            {
                "grade": 3.14,
                "student": {
                    "gpa": 3.99,
                    "person": {
                        "name": "Loren"
                    }
                }
            }
        ]
    }
    assert doc["_source"] == expected
