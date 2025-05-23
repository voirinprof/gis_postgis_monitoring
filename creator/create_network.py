import os
from sqlalchemy import create_engine, text
import geopandas as gpd
import pandas as pd
import pyproj

# the address file for the redis
qc_addresses_file = os.environ.get('DATA_ADDRESS')
# the streets file for neo4j
qc_streets_file = os.environ.get('DATA_STREETS')

# Construct the database URL
database_url = os.environ.get('DATABASE_URL')

# function to count the number of addresses and streets in the database
def count_infos_from_db():
    # connect to the database
    engine = create_engine(database_url)
    count_addresses = 0
    count_streets = 0

    # Check if the 'addresses' table exists
    with engine.connect() as conn:
        table_addresses_exist = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='addresses')"))
        
        table_streets_exist = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='streets')"))
        
        # if the table exists, count the number of rows
        if table_addresses_exist.scalar():
            # Count the number of addresses
            result = conn.execute(text("SELECT COUNT(*) FROM addresses"))
            count_addresses = result.scalar()

        # if the table exists, count the number of rows
        if table_streets_exist.scalar():
            # Count the number of streets
            result = conn.execute(text("SELECT COUNT(*) FROM streets"))
            count_streets = result.scalar()
        

    return count_addresses, count_streets

# Initialize some example data on startup
def init_addresses():
    # load the addresses file
    gdf = gpd.read_file(qc_addresses_file)
    
    # connect to the database
    engine = create_engine(database_url)

    # import the data into the database
    gdf.to_postgis(
        name="addresses",
        con=engine,
        schema="public",
        if_exists="replace",  # Remplace la table si elle existe
        index=False
    )

    # create a spatial index on the geometry column
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX addresses_geometry_idx ON addresses USING GIST (geometry);"))
    

# function to initialize the network
# all roads are in the network (they are bidirectional)
def init_network():
    
    # load the streets file
    gdf = gpd.read_file(qc_streets_file)

    # check if the geometry is valid
    gdf['geometry'] = gdf['geometry'].apply(lambda geom: geom if geom.is_valid else geom.buffer(0))

    # convert the geometry to a single LineString if it is a MultiLineString
    gdf['geometry'] = gdf['geometry'].apply(
        lambda geom: geom.geoms[0] if geom.geom_type == 'MultiLineString' else geom
    )

    # add the columns for the topology (source, target, cost)
    gdf['source'] = pd.Series([None] * len(gdf), dtype='Int32')  # Nullable integer
    gdf['target'] = pd.Series([None] * len(gdf), dtype='Int32')  # Nullable integer
    gdf['cost'] = gdf['geometry'].length  # Coût basé sur la longueur
    
    # connect to the database
    engine = create_engine(database_url)

    # import the data into the database
    gdf.to_postgis(
        name="streets",
        con=engine,
        schema="public",
        if_exists="replace",  # Remplace la table si elle existe
        index=False
    )
    
    # create a spatial index
    with engine.connect() as conn:
        # create the topology
        
        try:
            # use the pgr_createTopology function to create the topology
            result = conn.execute(text("""
                SELECT pgr_createTopology(
                    'streets', 
                    1,
                    'geometry',
                    'OBJECTID',
                    'source',
                    'target'
                );
            """))
            # table -> streets
            # snapping_tolerance -> 1 m (because the data is in meters)
            # id of the edge -> OBJECTID
            conn.commit()  # valid the transaction
            
            
        except Exception as e:
            
            return


        # Check if the topology was created successfully
        result = conn.execute(text("""
            SELECT pgr_analyzeGraph(
                'streets',
                1,
                'geometry',
                'OBJECTID',
                'source',
                'target'
            );
        """))
        conn.commit()

        
    

# check if the database is empty
cnt_addresses, cnt_streets = count_infos_from_db()


# check if the address file exists
if cnt_addresses == 0:
    init_addresses()
# check if the network exists
if cnt_streets == 0:
    init_network()   