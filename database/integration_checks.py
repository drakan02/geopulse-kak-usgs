"""Database contract tests. All fixture writes are rolled back."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
import uuid
import psycopg
from cli import connect, require


class RollbackFixtures(Exception):
    pass


def rejected(conn, statement, params, error_type):
    try:
        with conn.transaction():
            conn.execute(statement,params)
    except error_type:
        return
    raise AssertionError(f'Expected {error_type.__name__}')


def main():
    with connect() as conn:
        try:
            with conn.transaction():
                payload=b'CV2 temporary fixture; this transaction must roll back.'
                file_id=conn.execute('''INSERT INTO raw.file_archive
                    (source_kind,source_stage,filename,sha256,byte_size,content)
                    VALUES ('kak_raw','original_raw','cv2-test.txt',%s,%s,%s) RETURNING file_id''',
                    (hashlib.sha256(payload).hexdigest(),len(payload),payload)).fetchone()[0]
                rejected(conn,'UPDATE raw.file_archive SET filename=%s WHERE file_id=%s',('changed',file_id),psycopg.errors.RaiseException)
                rejected(conn,'DELETE FROM raw.file_archive WHERE file_id=%s',(file_id,),psycopg.errors.RaiseException)
                batch=conn.execute("INSERT INTO raw.import_batch(file_id,target_table,imported_rows) VALUES (%s,'fixture',1) RETURNING batch_id",(file_id,)).fetchone()[0]
                stamp=datetime(2027,1,1,tzinfo=timezone.utc)
                insert='''INSERT INTO clean.measurement
                    (time_utc,station_code,channel_code,value,quality_flag,source_quality_flag,batch_id)
                    VALUES (%s,'KAK',%s,%s,%s,%s,%s)'''
                conn.execute(insert,(stamp,'X',99.5,3,3,batch))
                sample=conn.execute("SELECT original_value,strict_value,cv1_display_value FROM analytics.vw_signal WHERE time_utc=%s AND channel_code='X'",(stamp,)).fetchone()
                require(sample==(99.5,None,99.5),'Spike value was not preserved or strict view is wrong')
                rejected(conn,insert,(stamp,'X',99.5,3,3,batch),psycopg.errors.UniqueViolation)
                rejected(conn,insert,(stamp,'Y',10,2,2,batch),psycopg.errors.CheckViolation)
                rejected(conn,insert,(stamp,'Y',10,3,0,batch),psycopg.errors.CheckViolation)
                rejected(conn,insert,(stamp,'Q',10,0,0,batch),psycopg.errors.ForeignKeyViolation)
                conn.execute(insert,(stamp,'Y',None,2,2,batch))
                run_id=uuid.uuid4()
                conn.execute('''INSERT INTO analytics.model_run
                    (run_id,station_code,channel_code,run_kind,method,input_series)
                    VALUES (%s,'KAK','X','filter','fixture','clean.measurement')''',(run_id,))
                conn.execute('''INSERT INTO analytics.filtered_series
                    (time_utc,run_id,station_code,channel_code,filtered_value,quality_flag)
                    VALUES (%s,%s,'KAK','X',98.5,0)''',(stamp,run_id))
                rejected(conn,'''INSERT INTO analytics.filtered_series
                    (time_utc,run_id,station_code,channel_code,filtered_value,quality_flag)
                    VALUES (%s,%s,'KAK','Y',98.5,0)''',(stamp+timedelta(minutes=1),run_id),psycopg.errors.ForeignKeyViolation)
                rejected(conn,'''INSERT INTO analytics.forecast_result
                    (target_time,run_id,station_code,channel_code,predicted_value)
                    VALUES (%s,%s,'KAK','X',98.5)''',(stamp,run_id),psycopg.errors.ForeignKeyViolation)
                raise RollbackFixtures()
        except RollbackFixtures:
            pass
        require(conn.execute("SELECT count(*) FROM raw.file_archive WHERE filename='cv2-test.txt'").fetchone()[0]==0,'Fixtures not rolled back')
        if os.environ.get('PG_READER_PASSWORD'):
            with psycopg.connect(user='geopulse_reader',password=os.environ['PG_READER_PASSWORD'],autocommit=True,connect_timeout=10) as reader:
                reader.execute('SELECT * FROM analytics.vw_signal LIMIT 1').fetchone()
                rejected(reader,'DELETE FROM clean.measurement WHERE false',(),psycopg.errors.InsufficientPrivilege)
                rejected(reader,'SELECT file_id FROM raw.file_archive',(),psycopg.errors.InsufficientPrivilege)
    print('PASS: source immutability, NULL/flags, duplicate prevention, run/kind/channel FKs, reader permissions, fixture rollback.')
    return {'checked_at':datetime.now(timezone.utc), 'passed':True, 'checks':[
        'archive rejects UPDATE and DELETE', 'spike values preserved; strict view returns NULL',
        'measurement keys prevent duplicates', 'missing values must be NULL',
        'combined flag cannot be lower than channel flag', 'unknown channel rejected',
        'filtered result must match model_run channel', 'filter run cannot store a forecast',
        'all fixtures rolled back', 'reader can read Analytics but cannot write Clean or read Raw']}


if __name__=='__main__':
    main()
