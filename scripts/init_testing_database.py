import argparse
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session
# from epanet_adapter.orm import EpanetBase, EpanetProject
from models import WorkflowsBase

import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

def init_testing_database(db_url, reset_db=False, init_with_project=False):
    """
    Initialize a postgresql database with empty epanet tables.
    """
    engine = create_engine(db_url)
    sqlalchemy_url = engine.url

    print("Initialize testing database: {}".format(sqlalchemy_url.database))

    if reset_db:
        print("Removing database tables...")
        # Clear out the Database
        meta = MetaData()
        meta.reflect(bind=engine)

        for table in reversed(meta.sorted_tables):
            if table.name != 'spatial_ref_sys':
                table.drop(engine)

    # Initialize postgis
    print("Creating postgis extension...")
    engine.execute('CREATE EXTENSION IF NOT EXISTS postgis;')

    # Create Tables / Initialize DB
    print("Creating epanet tables...")
    WorkflowsBase.metadata.create_all(engine)

    engine.dispose()
    print("Successfully initialized testing database: {}".format(sqlalchemy_url.database))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create/reset a epanet database for testing.')
    parser.add_argument(
        'db_url', type=str,
        help='An SQLAlchemy url to be used to make connection with database. Must provide a superuser connection. '
             'e.g. postgresql://<username>:<password>@<host>:<port>/<db_name>'
    )

    parser.add_argument(
        '-r', dest='reset', action='store_true',
        help='Reset the epanet database by removing all tables and creating empty ones.'
    )

    parser.add_argument(
        '-i', dest='init_with_project', action='store_true',
        help='Initialize the epanet database with an existing project. Only valid with reset option.'
    )
    parser.set_defaults(reset=False, init_with_project=False)

    args = parser.parse_args()

    init_testing_database(args.db_url, args.reset, args.init_with_project)






