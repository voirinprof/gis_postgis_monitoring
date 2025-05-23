# import the necessary libraries
from flask import Flask, jsonify, request

import os
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
import pyproj
from pyproj import Proj, transform

import logging
from logging.handlers import RotatingFileHandler
import json

app = Flask(__name__)

# create dir logs if not exists
if not os.path.exists('/app/logs'):
    os.makedirs('/app/logs')

# Configure logging
logger = logging.getLogger('flask_app')
logger.setLevel(logging.DEBUG)

# Create a file handler for logging
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler for console output
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Handler for file output with rotation
file_handler = RotatingFileHandler('/app/logs/app.log', maxBytes=1000000, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# the database url
database_url = os.environ.get('DATABASE_URL')

 
# create the transformer to convert from WGS84 to Quebec Lambert 32187
transformer_4326_32187 = pyproj.Transformer.from_crs(4326, 32187, always_xy=True)
# create the transformer to convert from Quebec Lambert 32187 to WGS84
transformer_32187_4326 = pyproj.Transformer.from_crs(32187, 4326, always_xy=True)

# function to search for addresses in the database
def addressSearch(query):
    
    suggestions = []
    
    # create query on the database to select the address like the text
    
    engine = create_engine(database_url)
    
    with engine.connect() as conn:

        # create the query
        sql_query = text(f"""
            SELECT "ADRESSE" as display_name, ST_Y(geometry) AS latitude, ST_X(geometry) AS longitude
            FROM addresses
            WHERE "ADRESSE" ILIKE :name
        """)
        
        # execute the query
        result = conn.execute(sql_query, {'name': f'%{query}%'})
        
        # fetch all results
        rows = result.fetchall()
        
        # create the suggestions list
        for row in rows:
            suggestions.append({
                "display_name": row[0],
                "lat": row[1],
                "lon": row[2]
            })

    return suggestions

# function to search for nodes in Neo4j
def nodeSearch(latitude, longitude):
    
    locations = []
    x, y = transformer_4326_32187.transform(float(longitude), float(latitude))
    
    engine = create_engine(database_url)
    # find the closest node to the address
    # according the location of the address
    # we will use the <-> operator to find the closest node
    # the <-> operator is KNN search operator
    with engine.connect() as conn:
        # create the query
        query = text("""
            SELECT id, ST_X(the_geom) AS longitude, ST_Y(the_geom) AS latitude
            FROM public.streets_vertices_pgr
            ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 32187)
            LIMIT 1
        """)
        result = conn.execute(query, {'lon': x, 'lat': y}).fetchone()
        if result:

            lon, lat = transformer_32187_4326.transform(result[1], result[2])

            locations.append({
                'node_id': result[0],
                'longitude': lon,
                'latitude': lat,
                'x': result[1],
                'y': result[2]
            })
        
    
    return locations


# Define the Flask routes
# home route
@app.route('/', methods=['GET'])
def home():
    return {"status": "healthy"}, 200

# route to get the address suggestions
@app.route("/suggest")
def suggest():
    query = request.args.get("q", "").lower()
    if not query or len(query) < 2:
        return jsonify([])

    search_results = addressSearch(query)

    suggestions = [
        {"label": addr['display_name']}
        for addr in search_results
        if query in addr['display_name'].lower()
    ][:10] 

    return jsonify(suggestions)

# route to get the location of the address
@app.route("/location")
def location():
    query = request.args.get("q", "")
    if not query or len(query) < 2:
        return jsonify([])

    # call the addressSearch function
    suggestions = addressSearch(query)

    return jsonify(suggestions)

# route to get the node 
@app.route("/findnode")
def findnode():
    latitude = request.args.get("lat", "")
    longitude = request.args.get("lon", "")
    if not latitude or not longitude:
        return jsonify([])
    # call the nodeSearch function
    locations = nodeSearch(latitude, longitude)

    return jsonify(locations)

# route to get the path between two addresses
@app.route("/findpath")
def findpath():
    # get the start and end addresses from the request
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    if not start or not end :
        return jsonify([])
    # find the closest address to the start and end addresses
    suggest_start = addressSearch(start)
    suggest_end = addressSearch(end)
    
    # we will use the first address found
    if len(suggest_start) > 0:
        first = suggest_start[0]
        # find the closest node to the address    
        suggest_node_start = nodeSearch(first['lat'], first['lon'])
    
    # we will use the first address found
    if len(suggest_end) > 0:
        first = suggest_end[0]
        # find the closest node to the address
        suggest_node_end = nodeSearch(first['lat'], first['lon'])
    
    # we will use the first node found
    if len(suggest_node_start) > 0:
        first_node = suggest_node_start[0]
    # we will use the first node found
    if len(suggest_node_end) > 0:
        second_node = suggest_node_end[0]

        
    logger.debug(f"first_node: {first_node} ")
    logger.debug(f"second_node: {second_node} ")

    objectids = []
    path = []
    length = 0
    geojson_obj = {
        "type": "FeatureCollection",
        "features": []
    }
    # we will use the pgr_dijkstra function to find the shortest path
    # connect to the database
    engine = create_engine(database_url)
    with engine.connect() as conn:
        # create the query
        query = text(f"""
            SELECT d.seq, d.path_seq, d.node, d.edge, d.cost, s.geometry
            FROM pgr_dijkstra(
                'SELECT "OBJECTID" AS id, source, target, cost, cost as reverse_cost FROM streets',
                :start, :end,
                directed => true
            ) AS d
            JOIN streets AS s ON d.edge = s."OBJECTID";
        """)
        # get the path from the database in a geodataframe
        result = gpd.read_postgis(query, conn, geom_col='geometry', crs="EPSG:32187",
                                   params={'start': first_node['node_id'], 'end': second_node['node_id']})

        # reproject the geometry to WGS84
        result.to_crs(epsg=4326, inplace=True)    

    # geojson to display on the map
    geojson_obj = json.loads(result.to_json())
    # the total cost of the path
    length = result['cost'].sum()
    # the object ids of the edges
    objectids = result['edge'].tolist()
    # the node ids of the path
    path = result['node'].tolist()

    return jsonify({"objectids": objectids, "geojson": geojson_obj, "totalCost": length, "nodeNames": path})



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)