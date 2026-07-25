import uuid

from pospay.bulk_import.file_storage import read_uploaded_file, save_uploaded_file


def test_save_and_read_roundtrip():
    tenant_id = uuid.uuid4()
    upload_id = uuid.uuid4()
    data = b"email,security_group,password\nnew@example.com,Preparer,hunter2\n"

    path = save_uploaded_file(tenant_id, upload_id, "users.csv", data)

    assert read_uploaded_file(path) == data
    assert str(upload_id) in path
    assert path.endswith("users.csv")


def test_different_tenants_do_not_collide():
    upload_id = uuid.uuid4()
    path_a = save_uploaded_file(uuid.uuid4(), upload_id, "same-name.csv", b"a")
    path_b = save_uploaded_file(uuid.uuid4(), upload_id, "same-name.csv", b"b")

    assert path_a != path_b
    assert read_uploaded_file(path_a) == b"a"
    assert read_uploaded_file(path_b) == b"b"
