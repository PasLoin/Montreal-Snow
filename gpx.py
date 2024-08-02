import argparse
import real.plot_path as pl
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
    ps.add_argument("--city",
                    type=str,
                    help="Specify city to search.")
    ps.add_argument("--country",
                    type=str,
                    help="Specify country to search.")
    args = ps.parse_args()
    if args.city is None:
        city = "Ixelles"
        country = "Belgique"
        return city, country
    return args.city, args.country

def create_gpx(route, filename="output.gpx"):
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()

    for node in route:
        long, lat = cu.route_to_long_lat(G, [node])
        # Extract values from square brackets
        lat = lat[0] if isinstance(lat, list) else lat
        long = long[0] if isinstance(long, list) else long
        track_point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=long)
        gpx_segment.points.append(track_point)

    gpx_track.segments.append(gpx_segment)
    with open(filename, "w") as f:
        f.write(gpx.to_xml())

def main():
    global G  # Declare G as global
    city, country = parse_argument()
    if city is None or country is None:
        print("Please specify --city and --country")
        print("Example: --city Kremlin-Bicetre --country France")

    print("Specified city: ", city)
    print("Specified country: ", country)

    print("Getting map data from Osmnx")
    # Get the graph data from osmnx
    G = ox.graph_from_place(city + ', ' + country, network_type='drive')

    # Convert the graph to undirected
    G = ox.utils_graph.get_undirected(G)

    # Steps to solve the Chinese postman problem:
    print("Step 1: Calculate list of nodes with odd degree")
    nodes_odd_degree = gu.get_nodes_odd_degree(G)
    print("Step 2.1: Compute all possible pairs of odd degree nodes.")
    odd_node_pairs = gu.compute_pairs_of_odd_degree_nodes(nodes_odd_degree)
    print("Step 2.2: Compute the shortest path between each node pair calculated in 1.")
    odd_node_pairs_shortest_paths = ga.get_shortest_paths_distances(G, odd_node_pairs, 'distance')

    print("Step 2.3: Generate the complete graph")
    g_odd_complete = ga.create_complete_graph(odd_node_pairs_shortest_paths, flip_weights=True)

    node_positions = gu.get_node_position(G)

    pl.plot_complete_graph_odd_degree(g_odd_complete, node_positions)

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
    pl.plot_min_weight_matching_complete(g_odd_complete, g_odd_complete_min_edges, node_positions)
    pl.plot_min_weight_matching_original(G, g_odd_complete_min_edges, node_positions)

    route = cu.euler_circuit_to_route(euler_circuit)
    f = open("output.txt", "w")
    for edge in euler_circuit:
        if edge[2][0].get('name') is not None:
            name = edge[2][0].get('name')
            osmid = edge[2][0].get('osmid')
            f.write(f"Street Name: {name}, OSMID: {osmid}\n")

    long, lat = cu.route_to_long_lat(G, route)
    origin_point, dest_point = cu.long_lat_to_points(long, lat)
    f.write(f"Longitude: {long}\n")
    f.write(f"Latitude: {lat}\n")
    f.write(f"Origin Point: {origin_point}\n")
    f.write(f"Destination Point: {dest_point}\n")
    f.close()

    print("Plotting the route")
    pl.plot_path(lat, long, origin_point, dest_point)

    create_gpx(route)

if __name__ == '__main__':
    main()
