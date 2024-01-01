import argparse
import xml.etree.ElementTree as ET
import openrouteservice
import networkx as nx
import osmnx as ox
import real.graph_utils as gu
import real.graph_algo as ga
import real.convert_utils as cu
import real.stats as st
import gpxpy.gpx

# Make G a global variable
G = None

def parse_argument():
    ps = argparse.ArgumentParser(description="Big demo.")
    ps.add_argument("--city", type=str, help="Specify city to search.")
    ps.add_argument("--country", type=str, help="Specify country to search.")
    args = ps.parse_args()
    if args.city is None:
        city = "Matongé"
        country = "Belgique"
        return city, country
    return args.city, args.country

def create_gpx(route, filename="output.gpx"):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()

    for lon, lat in route:
        track_point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
        gpx_segment.points.append(track_point)

    gpx_track.segments.append(gpx_segment)
    with open(filename, "w") as f:
        f.write(gpx.to_xml())

def read_gpx_coordinates(gpx_file):
    tree = ET.parse(gpx_file)
    root = tree.getroot()

    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}

    coordinates = []
    for trkpt in root.findall('.//gpx:trkpt', ns):
        lat = float(trkpt.get('lat'))
        lon = float(trkpt.get('lon'))
        coordinates.append((lon, lat))

    return coordinates

def optimize_route(coordinates, api_key):
    ors_client = openrouteservice.Client(key=api_key)
    ors_route = ors_client.directions(
        coordinates=coordinates,
        profile='cycling-regular',
        format='geojson',
        validate=False,
        optimize_waypoints=True
    )
    return ors_route

def main():
    global G
    ORS_API_KEY = "Your_ORS_API_key_HERE"

    city, country = parse_argument()
    if city is None or country is None:
        print("Please specify --city and --country")
        print("Example: --city Matongé --country Belgique")

    print("Specified city: ", city)
    print("Specified country: ", country)

    print("Getting map data from Osmnx")
    G = ox.graph_from_place(city + ', ' + country, network_type='all')
    G = ox.utils_graph.get_undirected(G)

    print("Step 1: Calculate list of nodes with odd degree")
    nodes_odd_degree = gu.get_nodes_odd_degree(G)
    print("Step 2.1: Compute all possible pairs of odd degree nodes.")
    odd_node_pairs = gu.compute_pairs_of_odd_degree_nodes(nodes_odd_degree)
    print("Step 2.2: Compute the shortest path between each node pair calculated in 1.")
    odd_node_pairs_shortest_paths = ga.get_shortest_paths_distances(G, odd_node_pairs, 'distance')

    print("Step 2.3: Generate the complete graph")
    g_odd_complete = ga.create_complete_graph(odd_node_pairs_shortest_paths, flip_weights=True)

    print("Step 2.4: Compute Minimum Weight Matching")
    odd_matching_dupes = nx.algorithms.max_weight_matching(g_odd_complete, True)
    odd_matching = gu.remove_dupes_from_matching(odd_matching_dupes)

    g_aug = ga.add_augmenting_path_to_graph(G, odd_matching)

    print("Step 3.0: Compute Eulerian Circuit")
    s = g_aug.edges()
    source_s = gu.get_first_element_from_multi_edge_graphe(s)

    naive_eulerian = False
    if naive_eulerian:
        naive_euler_circuit = list(nx.eulerian_circuit(g_aug, source=source_s))
        euler_circuit = naive_euler_circuit
    else:
        euler_circuit = ga.create_eulerian_circuit(g_aug, G, source_s)

    st.stats(G, euler_circuit)

    g_odd_complete_min_edges = gu.get_nodes_odd_complete_min_edges(odd_matching)

    route_coordinates = [(G.nodes[u]['x'], G.nodes[u]['y']) for u, v, data in euler_circuit]

    print("Creating GPX file without optimization")
    create_gpx(route_coordinates, filename="output_without_optimization.gpx")

    print("Reading coordinates from GPX file")
    gpx_file = "output_without_optimization.gpx"
    coordinates = read_gpx_coordinates(gpx_file)

    print("Optimizing the route using OpenRouteService")
    chunk_size = 70
    chunks = [coordinates[i:i + chunk_size] for i in range(0, len(coordinates), chunk_size)]

    optimized_order = []
    for i, chunk in enumerate(chunks):
        print(f"Optimization successful for chunk {i + 1}/{len(chunks)}")
        try:
            ors_route = optimize_route(chunk, ORS_API_KEY)
            optimized_order.extend(ors_route['features'][0]['geometry']['coordinates'])
        except Exception as e:
            print(f"Optimization failed with error: {e}")

    print("Creating GPX file with optimization")
    create_gpx(optimized_order, filename="output_with_optimization.gpx")

if __name__ == "__main__":
    main()
