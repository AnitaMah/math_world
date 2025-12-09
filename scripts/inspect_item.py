import sqlite3
import sys
conn=sqlite3.connect('db.sqlite3')
c=conn.cursor()
item_id=115
if len(sys.argv)>1:
    item_id=int(sys.argv[1])
c.execute('SELECT id, paragraph_id, number FROM education_item WHERE id=?',(item_id,))
row=c.fetchone()
print('item row:', row)
if row:
    pid=row[1]
    c.execute('SELECT id, section_id, number FROM education_paragraph WHERE id=?',(pid,))
    pr=c.fetchone()
    print('paragraph row:', pr)
    if pr:
        sid=pr[1]
        c.execute('SELECT id, grade_id, number FROM education_section WHERE id=?',(sid,))
        sec=c.fetchone()
        print('section row:', sec)
conn.close()
