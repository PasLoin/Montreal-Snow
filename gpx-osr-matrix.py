import argparse
import real.plot_path as pl
import networkx as nx
import osmnx as ox
import real.graph_utils as gu
import real.graph_algo as ga
import real.convert_utils as cu
import real.stats as st
import gpxpy.gpx
import csv
import requests
import time

# Make G a global variable
G = None

# Replace this with your OpenRouteService API key
API_KEY = "Replace this with your OpenRouteService API key"

def parse_argument():
    ps = argparse.ArgumentParser(description="Big demo.")
    ps.add_argument("--city", type=str, help="Specify city to search.")
    ps.add_argument("--country", type=str, help="Specify country to search.")
    args = ps.parse_args()
    if args.city is None:
        city = "Marolles"
        country = "Belgique"
        return city, country
    return args.city, args.country

def optimize_routes_with_ors(coordinates, profile="driving-car", batch_size=40, delay_seconds=90):
    url_matrix = f"https://api.openrouteservice.org/v2/matrix/{profile}"

    durations_matrix = []

    for i in range(0, len(coordinates), batch_size):
        batch_coordinates = coordinates[i:i+batch_size]

        params_matrix = {
            "locations": batch_coordinates,
        }

        headers_matrix = {
            "Authorization": f"Bearer {API_KEY}"
        }

        response_matrix = requests.post(url_matrix, json=params_matrix, headers=headers_matrix)
        data_matrix = response_matrix.json()

        if "error" in data_matrix:
            print(f"Matrix API Error: {data_matrix['error']}")
            return None

        batch_durations_matrix = data_matrix.get('durations')

        if batch_durations_matrix is None:
            print("Error: Could not retrieve durations matrix from the Matrix API response.")
            return None

        durations_matrix.extend(batch_durations_matrix)

        # Introduce delay to comply with the rate limit
        time.sleep(delay_seconds)

    return durations_matrix

def process_matrix_result(matrix_result):
    if not isinstance(matrix_result, list):
        print("Error: Invalid matrix_result format")
        return []

    optimized_sequences = []

    for row in matrix_result:
        if not isinstance(row, list):
            print("Error: Invalid matrix_result row format")
            continue

        min_time_index = row.index(min(row))
        optimized_sequences.append(min_time_index)

    return optimized_sequences

def process_directions_result(directions_result):
    if "features" not in directions_result:
        print("Error: Invalid Directions API response format")
        return

    route = directions_result["features"][0]["properties"]["segments"][0]["steps"]
    min_travel_time = min(step["duration"] for step in route)

    print(f"Minimum Travel Time for this Route: {min_travel_time} seconds")

    return min_travel_time

def aggregate_and_display_results(min_travel_times):
    # For example, display the total minimum travel time for all routes
    total_min_travel_time = sum(min_travel_times)
    print(f"Total Minimum Travel Time for All Routes: {total_min_travel_time} seconds")

def get_coordinates_from_euler_circuit(g, euler_circuit):
    coordinates = []

    for edge in euler_circuit:
        node = edge[0]
        long, lat = cu.route_to_long_lat(g, [node])
        lat = lat[0] if isinstance(lat, list) else lat
        long = long[0] if isinstance(long, list) else long
        coordinates.append([long, lat])

    return coordinates

def export_to_csv(route, filename="output.csv"):
    with open(filename, "w", newline="") as csvfile:
        fieldnames = ["Latitude", "Longitude"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()

        for node in route:
            long, lat = cu.route_to_long_lat(G, [node])
            lat = lat[0] if isinstance(lat, list) else lat
            long = long[0] if isinstance(long, list) else long
            writer.writerow({"Latitude": lat, "Longitude": long})

def main():
    global G

    # Step 1: Parse Arguments
    city, country = parse_argument()

    if city is None or country is None:
        print("Please specify --city and --country")
        print("Example: --city Kremlin-Bicetre --country France")

    print("Specified city: ", city)
    print("Specified country: ", country)

    # Step 2: Get Map Data
    print("Getting map data from Osmnx")
    G = ox.graph_from_place(city + ', ' + country, network_type='drive')
    G = ox.utils_graph.get_undirected(G)

    # Steps 3-4: Chinese Postman Problem and Eulerian Circuit
    print("Solving the Chinese Postman Problem")
    nodes_odd_degree = gu.get_nodes_odd_degree(G)
    odd_node_pairs = gu.compute_pairs_of_odd_degree_nodes(nodes_odd_degree)
    odd_node_pairs_shortest_paths = ga.get_shortest_paths_distances(G, odd_node_pairs, 'distance')
    g_odd_complete = ga.create_complete_graph(odd_node_pairs_shortest_paths, flip_weights=True)
    node_positions = gu.get_node_position(G)

    # Step 5: Compute Minimum Weight Matching
    odd_matching_dupes = nx.algorithms.max_weight_matching(g_odd_complete, True)
    odd_matching = gu.remove_dupes_from_matching(odd_matching_dupes)
    g_aug = ga.add_augmenting_path_to_graph(G, odd_matching)

    # Step 6: Compute Eulerian Circuit
    s = g_aug.edges()
    source_s = gu.get_first_element_from_multi_edge_graphe(s)

    naive_eulerian = False
    if naive_eulerian:
        naive_euler_circuit = list(nx.eulerian_circuit(g_aug, source=source_s))
        euler_circuit = naive_euler_circuit
    else:
        euler_circuit = ga.create_eulerian_circuit(g_aug, G, source_s)

    # Step 7: Display Statistics
    st.stats(G, euler_circuit)

    # Step 8: Plotting
    g_odd_complete_min_edges = gu.get_nodes_odd_complete_min_edges(odd_matching)
    pl.plot_min_weight_matching_complete(g_odd_complete, g_odd_complete_min_edges, node_positions)
    pl.plot_min_weight_matching_original(G, g_odd_complete_min_edges, node_positions)

    # Step 9: Get Coordinates from Eulerian Circuit
    coordinates = get_coordinates_from_euler_circuit(G, euler_circuit)

    # Step 10: Optimize Routes with Matrix API
    matrix_result = optimize_routes_with_ors(coordinates, profile="driving-car")

    if matrix_result is None:
        exit()

    # Process Matrix Result
    optimized_sequences = process_matrix_result(matrix_result)

    # Step 11: Display Minimum Travel Time for Each Route
    min_travel_times = []
    for seq_index in optimized_sequences:
        print("Current Sequence Index:", seq_index)  # Add this print statement
        start = seq_index
        end = seq_index + 1  # Assuming you want a single element, adjust as needed
        coordinates_subset = coordinates[start:end]
        directions_url = f"https://api.openrouteservice.org/v2/directions/driving-car?coordinates={coordinates_subset}&format=geojson&api_key={API_KEY}"
        response_directions = requests.get(directions_url)
        data_directions = response_directions.json()
        min_travel_time = process_directions_result(data_directions)
        min_travel_times.append(min_travel_time)

    # Step 12: Aggregate and Display Results
    aggregate_and_display_results(min_travel_times)

    # Step 13: Additional Output
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

    # Additional output to CSV
    export_to_csv(route)

if __name__ == '__main__':
    main()
