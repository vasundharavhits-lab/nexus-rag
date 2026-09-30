from app import db, indexing

def main():
    con = db.connect()
    db.init_db(con)                      # creates the new chunks table
    print(indexing.index_workspace(con, "demo-workspace"))

if __name__ == "__main__":
    main()