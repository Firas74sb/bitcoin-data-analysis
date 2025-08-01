import os
import re
import json
import math
import time
from datetime import datetime
from pathlib import Path
from flask import render_template, request, send_from_directory, jsonify
from pyvis.network import Network
from community import community_louvain
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import polars as pl
import networkx as nx

# Constants
MIN_DATE = datetime(2009, 1, 3)
MAX_DATE = datetime(2021, 1, 25)
PARQUET_DIR = 'data/SNAPSHOT/EDGES/hour'
HOUR_CACHE = {}

# Create generated files directory
GENERATED_DIR = Path(__file__).parent / 'generated'
GENERATED_DIR.mkdir(exist_ok=True)

# Color constants
TOP_SPENDER_COLOR = "#FF5733"
TOP_RECEIVER_COLOR = "#33FF57"
TOP_BOTH_COLOR = "#3357FF"
COMMUNITY_HIGHLIGHT_COLOR = "#FF33F5"

def register_context(app):
    # Template filters
    @app.template_filter('format_satoshi')
    def format_satoshi(value):
        try:
            return f"{int(value):,}"
        except (ValueError, TypeError):
            return "N/A"

    @app.template_filter('format_usd')
    def format_usd(value):
        try:
            return f"${float(value):,.2f}"
        except (ValueError, TypeError):
            return "N/A"

    @app.template_filter('satoshi_to_btc')
    def satoshi_to_btc(satoshi):
        try:
            return float(satoshi) * 0.00000001
        except (ValueError, TypeError):
            return 0

    @app.template_filter('unique')
    def unique_filter(sequence):
        seen = set()
        return [x for x in sequence if not (x in seen or seen.add(x))]

    @app.template_filter('hash')
    def hash_filter(s):
        if not s:
            return 0
        return abs(hash(s))

    def validate_date(date_obj):
        if date_obj < MIN_DATE or date_obj > MAX_DATE:
            raise ValueError(f"Date must be between {MIN_DATE.strftime('%Y-%m-%d')} and {MAX_DATE.strftime('%Y-%m-%d')}")

    def extract_hour_from_filename(filename):
        match = re.search(r'date-\d{4}-\d{2}-\d{2}-(\d{2})', filename)
        return int(match.group(1)) if match else None

    def parallel_get_hours(date_str):
        try:
            if date_str in HOUR_CACHE:
                return HOUR_CACHE[date_str]
            
            year, month, day = map(int, date_str.split('-'))
            prefix = f"orbitaal-snapshot-date-{year}-{month:02d}-{day:02d}-"
            
            with ThreadPoolExecutor() as executor:
                files = [f for f in os.listdir(PARQUET_DIR) 
                        if f.startswith(prefix) and f.endswith('.snappy.parquet')]
                
                hours = {extract_hour_from_filename(f) for f in files}
                hours = {h for h in hours if h is not None and 0 <= h <= 23}
                
            result = {
                "date": date_str,
                "available_hours": sorted(hours),
                "message": "OK" if hours else "No data found"
            }
            
            HOUR_CACHE[date_str] = result
            return result
            
        except Exception as e:
            return {"error": str(e)}

    @app.route('/get-hours/<date_str>')
    def get_available_hours(date_str):
        try:
            result = parallel_get_hours(date_str)
            if 'error' in result:
                return jsonify(result), 500
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    def load_hour_data(date_obj, hour):
        try:
            year = date_obj.year
            month = date_obj.month
            day = date_obj.day
            
            pattern = f"orbitaal-snapshot-date-{year}-{month:02d}-{day:02d}-{hour:02d}-*.snappy.parquet"
            files = [os.path.join(PARQUET_DIR, f) for f in os.listdir(PARQUET_DIR) 
                    if f.startswith(f"orbitaal-snapshot-date-{year}-{month:02d}-{day:02d}-{hour:02d}-") 
                    and f.endswith(".snappy.parquet")]
            
            if not files:
                return None, None
            
            files.sort(key=lambda x: int(x.split('-')[-1].split('.')[0]))
            full_df = pl.concat([pl.read_parquet(file) for file in files])
            
            if full_df.is_empty():
                return None, None
                
            graph_df = full_df.sort("VALUE_SATOSHI", descending=True).head(1000)
            return full_df, graph_df
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            return None, None

    def calculate_stats(full_df, graph_df):
        if full_df is None or full_df.is_empty():
            return None, None, None
            
        full_src = set(full_df["SRC_ID"].cast(str))
        full_dst = set(full_df["DST_ID"].cast(str))
        hour_stats = {
            'total_nodes': len(full_src.union(full_dst)),
            'total_transactions': len(full_df),
            'avg_satoshi': full_df["VALUE_SATOSHI"].mean(),
            'total_satoshi': full_df["VALUE_SATOSHI"].sum(),
            'avg_usd': full_df["VALUE_USD"].mean()
        }
        
        graph_stats = {}
        node_transactions = []
        
        if graph_df is not None and not graph_df.is_empty():
            graph_src = set(graph_df["SRC_ID"].cast(str))
            graph_dst = set(graph_df["DST_ID"].cast(str))
            
            node_transactions = graph_df.select([
                pl.col("SRC_ID").cast(str).alias("node"),
                pl.col("DST_ID").cast(str).alias("counterparty"),
                pl.col("VALUE_SATOSHI"),
                pl.col("VALUE_USD")
            ]).rows(named=True)
            
            graph_stats = {
                'shown_nodes': len(graph_src.union(graph_dst)),
                'shown_transactions': len(graph_df),
                'pct_transactions': (len(graph_df)/hour_stats['total_transactions'])*100 if hour_stats['total_transactions'] > 0 else 0,
                'max_satoshi': graph_df["VALUE_SATOSHI"].max(),
                'min_satoshi': graph_df["VALUE_SATOSHI"].min(),
                'node_transactions': node_transactions
            }
        
        return hour_stats, graph_stats, node_transactions

    def analyze_money_flow(full_df):
        if full_df is None or full_df.is_empty():
            return None, None
        
        filtered_df = full_df.filter(pl.col("SRC_ID") != pl.col("DST_ID"))
        
        spenders = filtered_df.group_by("SRC_ID").agg(
            pl.col("VALUE_SATOSHI").sum().alias("total_spent"),
            pl.col("VALUE_USD").sum().alias("total_spent_usd")
        ).sort("total_spent", descending=True).head(3)
        
        receivers = filtered_df.group_by("DST_ID").agg(
            pl.col("VALUE_SATOSHI").sum().alias("total_received"),
            pl.col("VALUE_USD").sum().alias("total_received_usd")
        ).sort("total_received", descending=True).head(3)
        
        return spenders.to_dicts(), receivers.to_dicts()

    def analyze_topology(graph_df, communities=None):
        if graph_df is None or graph_df.is_empty():
            return {}, set()
        
        G = nx.DiGraph()
        for row in graph_df.rows():
            src, dst, satoshi, usd = row
            G.add_edge(str(src), str(dst), weight=satoshi)
        
        metrics = {
            'density': nx.density(G),
            'average_clustering': nx.average_clustering(G.to_undirected()),
            'is_connected': nx.is_weakly_connected(G),
            'number_strongly_connected_components': nx.number_strongly_connected_components(G),
            'number_weakly_connected_components': nx.number_weakly_connected_components(G)
        }
        
        undirected = G.to_undirected()
        betweenness = nx.betweenness_centrality(undirected)
        bridge_nodes = set(node for node in betweenness if betweenness[node] > 0.1)
        
        return metrics, bridge_nodes

    def get_community_sizes(communities):
        if not communities:
            return {}
        
        size_dist = defaultdict(int)
        for comm in communities.values():
            size_dist[comm] += 1
        
        return dict(sorted(size_dist.items(), key=lambda x: x[1], reverse=True))

    def calculate_node_balances(graph_df):
        if graph_df is None or graph_df.is_empty():
            return {}
        
        sent = graph_df.group_by("SRC_ID").agg(
            pl.col("VALUE_SATOSHI").sum().alias("sent")
        ).to_dicts()
        
        received = graph_df.group_by("DST_ID").agg(
            pl.col("VALUE_SATOSHI").sum().alias("received")
        ).to_dicts()
        
        balances = defaultdict(int)
        for node in sent:
            balances[str(node['SRC_ID'])] -= node['sent']
        for node in received:
            balances[str(node['DST_ID'])] += node['received']
        
        return dict(balances)

    def detect_changes(graph_df1, graph_df2):
        if graph_df1 is None or graph_df1.is_empty() or graph_df2 is None or graph_df2.is_empty():
            return {}
        
        nodes1 = set(graph_df1["SRC_ID"].cast(str)).union(set(graph_df1["DST_ID"].cast(str)))
        nodes2 = set(graph_df2["SRC_ID"].cast(str)).union(set(graph_df2["DST_ID"].cast(str)))
        
        edges1 = set((str(row[0]), str(row[1])) for row in graph_df1.rows())
        edges2 = set((str(row[0]), str(row[1])) for row in graph_df2.rows())
        
        return {
            'new_nodes': nodes2 - nodes1,
            'disappeared_nodes': nodes1 - nodes2,
            'common_nodes': nodes1 & nodes2,
            'new_edges': edges2 - edges1,
            'disappeared_edges': edges1 - edges2,
            'common_edges': edges1 & edges2
        }

    def name_communities(communities):
        if not communities:
            return {}
        
        comm_counts = defaultdict(int)
        for comm in communities.values():
            comm_counts[comm] += 1
        
        sorted_comms = sorted(comm_counts.items(), key=lambda x: x[1], reverse=True)
        comm_names = {comm_id: f"c{i+1}" for i, (comm_id, _) in enumerate(sorted_comms)}
        named_communities = {str(node): comm_names[comm] for node, comm in communities.items()}
        return named_communities

    def get_top_communities(graph_df, communities, n=3):
        if graph_df is None or graph_df.is_empty() or not communities:
            return {}, {}
        
        node_to_comm = communities
        comm_spent = defaultdict(int)
        comm_received = defaultdict(int)
        
        for row in graph_df.rows():
            src, dst, satoshi, usd = row
            src = str(src)
            dst = str(dst)
            if src in node_to_comm and dst in node_to_comm:
                comm_spent[node_to_comm[src]] += satoshi
                comm_received[node_to_comm[dst]] += satoshi
        
        top_spenders = dict(sorted(comm_spent.items(), key=lambda x: x[1], reverse=True)[:n])
        top_receivers = dict(sorted(comm_received.items(), key=lambda x: x[1], reverse=True)[:n])
        
        return top_spenders, top_receivers

    def generate_search_view(net, G, communities, search_query, spender_ids, receiver_ids, community_view):
        try:
            search_node = str(int(search_query))
            if search_node in G.nodes():
                ego = nx.ego_graph(G, search_node, radius=2, undirected=True)
                pos = nx.spring_layout(ego, center=[0,0], scale=1, k=0.5/math.sqrt(len(ego.nodes())))
                
                top_both = set(str(x) for x in spender_ids) & set(str(x) for x in receiver_ids)
                top_spenders_only = set(str(x) for x in spender_ids) - top_both
                top_receivers_only = set(str(x) for x in receiver_ids) - top_both
                
                for node in ego.nodes():
                    dist = math.sqrt(pos[node][0]**2 + pos[node][1]**2)
                    size = max(5, 30 - dist*15)
                    
                    title = f"Node {node}"
                    color = "rgb(100,100,100)"
                    
                    if community_view and communities:
                        comm = communities.get(node, '')
                        hue = (abs(hash(comm)) % 360) if comm else 0
                        color = f"hsl({hue}, 70%, 50%)"
                        title += f"\nCommunity: {comm}"
                    
                    if node == search_node:
                        color = "rgb(255,0,0)"
                        size = 30
                        title += "\nSearched Node"
                    elif node in top_both:
                        color = TOP_BOTH_COLOR
                        size = max(15, size)
                        title += "\nTop Spender & Receiver"
                    elif node in top_spenders_only:
                        color = TOP_SPENDER_COLOR
                        size = max(12, size)
                        title += "\nTop Spender"
                    elif node in top_receivers_only:
                        color = TOP_RECEIVER_COLOR
                        size = max(12, size)
                        title += "\nTop Receiver"
                    
                    net.add_node(node, 
                                label=node, 
                                color=color, 
                                title=title, 
                                size=size,
                                x=pos[node][0]*1000,
                                y=pos[node][1]*1000)
                
                for src, dst, data in ego.edges(data=True):
                    comm_src = communities.get(src, '') if communities else ''
                    comm_dst = communities.get(dst, '') if communities else ''
                    net.add_edge(src, dst, 
                                title=f"From: {src} ({comm_src})\nTo: {dst} ({comm_dst})\nValue: {data['weight']:,} SAT\n≈ ${data['usd']:,.2f} USD",
                                arrows='to')
                
                filename = f"search_{search_node}_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
                net.save_graph(str(GENERATED_DIR / filename))
                return filename, communities
                
        except ValueError:
            if not community_view or not communities:
                raise ValueError("Community search only available in community view")
            
            comm_id = search_query
            members = [n for n, c in communities.items() if c == comm_id]
            
            if not members:
                raise ValueError(f"Community '{comm_id}' not found")

            # Generate community-only view
            comm_filename = f"comm_{comm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
            comm_net = Network(height="400px", width="400px", directed=True, notebook=False)
            
            for node in members:
                title = f"Node {node}\nCommunity: {comm_id}"
                color = COMMUNITY_HIGHLIGHT_COLOR
                
                if node in spender_ids and node in receiver_ids:
                    color = TOP_BOTH_COLOR
                    title += "\nTop Spender & Receiver"
                elif node in spender_ids:
                    color = TOP_SPENDER_COLOR
                    title += "\nTop Spender"
                elif node in receiver_ids:
                    color = TOP_RECEIVER_COLOR
                    title += "\nTop Receiver"
                
                comm_net.add_node(node, label=node, color=color, title=title, size=15)
            
            for src, dst, data in G.edges(data=True):
                if src in members and dst in members:
                    comm_net.add_edge(src, dst, 
                                    title=f"From: {src}\nTo: {dst}\nValue: {data['weight']:,} SAT\n≈ ${data['usd']:,.2f} USD",
                                    arrows='to')

            comm_net.save_graph(str(GENERATED_DIR / comm_filename))
            
            # Generate main view with highlighted community
            main_filename = f"search_comm_{comm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
            main_path = GENERATED_DIR / main_filename
            
            with open(main_path, 'w') as f:
                f.write(f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Community {comm_id} Visualization</title>
                    <style>
                        body {{ margin: 0; padding: 0; overflow: hidden; }}
                        .container {{
                            display: flex;
                            width: 100vw;
                            height: 100vh;
                        }}
                        .main-network {{
                            flex: 1;
                            height: 100%;
                        }}
                        .community-network {{
                            position: absolute;
                            right: 20px;
                            bottom: 20px;
                            width: 400px;
                            height: 400px;
                            border: 2px solid #ccc;
                            border-radius: 8px;
                            overflow: hidden;
                            background: white;
                            z-index: 1000;
                        }}
                        iframe {{
                            width: 100%;
                            height: 100%;
                            border: none;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="main-network">
                            <iframe src="/network/{net.path}"></iframe>
                        </div>
                        <div class="community-network">
                            <iframe src="/community/{comm_net.path}"></iframe>
                        </div>
                    </div>
                </body>
                </html>
                """)
            
            return main_filename, communities

    def generate_normal_network(graph_df, spender_ids, receiver_ids, community_view, communities):
        G = nx.DiGraph()
        max_satoshi = graph_df["VALUE_SATOSHI"].max()
        
        for row in graph_df.rows():
            src, dst, satoshi, usd = row
            G.add_edge(str(src), str(dst), weight=satoshi, usd=usd)
        
        net = Network(height="900px", width="100%", directed=True, notebook=False)
        
        top_both = set(str(x) for x in spender_ids) & set(str(x) for x in receiver_ids)
        top_spenders_only = set(str(x) for x in spender_ids) - top_both
        top_receivers_only = set(str(x) for x in receiver_ids) - top_both
        
        for node in G.nodes():
            title = f"Node {node}"
            color = "rgb(100,100,100)"
            size = 10
            
            if community_view and communities:
                comm = communities.get(node, '')
                hue = (abs(hash(comm)) % 360) if comm else 0
                color = f"hsl({hue}, 70%, 50%)"
                title += f"\nCommunity: {comm}"
            
            if node in top_both:
                color = TOP_BOTH_COLOR
                size = 20
                title += "\nTop Spender & Receiver"
            elif node in top_spenders_only:
                color = TOP_SPENDER_COLOR
                size = 15
                title += "\nTop Spender"
            elif node in top_receivers_only:
                color = TOP_RECEIVER_COLOR
                size = 15
                title += "\nTop Receiver"
            elif node == "0":
                color = "rgb(255,0,0)"
                size = 100
                title += "\nSpecial Node"
            
            net.add_node(node, label=node, color=color, title=title, size=size)
        
        for src, dst, data in G.edges(data=True):
            width = 0.5 + (data['weight'] / max_satoshi) * 2.5
            comm_src = communities.get(src, '') if communities else ''
            comm_dst = communities.get(dst, '') if communities else ''
            title = f"From: {src} ({comm_src})\nTo: {dst} ({comm_dst})\nValue: {data['weight']:,} SAT\n≈ ${data['usd']:,.2f} USD"
            net.add_edge(src, dst, title=title, arrows='to', width=width)
        
        physics = {
            'solver': 'forceAtlas2Based',
            'forceAtlas2Based': {
                'gravitationalConstant': -100,
                'centralGravity': 0.01,
                'springLength': 100,
                'damping': 0.4,
                'avoidOverlap': 0.5
            }
        }
        
        if community_view:
            physics['forceAtlas2Based']['springConstant'] = 0.01
        
        net.set_options(f"""
        {{
            "physics": {json.dumps(physics)}
        }}
        """)
        
        filename = f"network_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
        net.save_graph(str(GENERATED_DIR / filename))
        return filename, communities

    def generate_network(graph_df, spender_ids, receiver_ids, community_view=False, search_query=None, communities=None):
        if graph_df is None or graph_df.is_empty():
            return None, None
            
        try:
            G = nx.DiGraph()
            for row in graph_df.rows():
                src, dst, satoshi, usd = row
                G.add_edge(str(src), str(dst), weight=satoshi, usd=usd)
            
            # Community detection
            undirected = G.to_undirected()
            numeric_communities = community_louvain.best_partition(undirected)
            communities = name_communities(numeric_communities)
            
            # Handle community search
            if search_query and community_view:
                if search_query.startswith('c'):
                    # Search for community
                    members = [n for n, c in communities.items() if c == search_query]
                    if members:
                        return generate_community_subgraph(G, communities, search_query, spender_ids, receiver_ids)
            
            # Handle node search
            if search_query:
                try:
                    search_node = str(int(search_query))
                    if search_node in G.nodes():
                        return generate_search_view(Network(height="900px", width="100%", directed=True, notebook=False), 
                                                G, communities, search_node, spender_ids, receiver_ids, community_view)
                except ValueError:
                    pass
            
            # Generate normal network view
            if community_view:
                return generate_community_view(G, communities, spender_ids, receiver_ids)
            else:
                return generate_normal_network(graph_df, spender_ids, receiver_ids, community_view, communities)
        
        except Exception as e:
            print(f"Error generating network: {str(e)}")
            return None, None

    def generate_community_view(G, communities, spender_ids, receiver_ids):
        net = Network(height="900px", width="100%", directed=True, notebook=False)
        
        # Group nodes by community
        community_nodes = defaultdict(list)
        for node in G.nodes():
            community_nodes[communities.get(node, '')].append(node)
        
        # Create community nodes
        for comm_id, members in community_nodes.items():
            # Calculate community stats
            total_nodes = len(members)
            total_value = sum(G.edges[src, dst]['weight'] 
                            for src in members for dst in G.neighbors(src))
            
            # Create community node
            net.add_node(comm_id,
                        label=f"Community {comm_id}",
                        title=f"Community {comm_id}\nNodes: {total_nodes}\nTotal Value: {total_value:,} SAT",
                        size=20 + math.log(total_nodes + 1) * 5,
                        color=f"hsl({(abs(hash(comm_id)) % 360)}, 70%, 50%)",
                        shape='box')
        
        # Create edges between communities
        comm_edges = defaultdict(int)
        for src, dst in G.edges():
            src_comm = communities.get(src, '')
            dst_comm = communities.get(dst, '')
            if src_comm != dst_comm:
                comm_edges[(src_comm, dst_comm)] += G.edges[src, dst]['weight']
        
        for (src_comm, dst_comm), weight in comm_edges.items():
            net.add_edge(src_comm, dst_comm,
                        value=weight,
                        title=f"From {src_comm} to {dst_comm}\nValue: {weight:,} SAT")
        
        filename = f"community_view_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
        net.save_graph(str(GENERATED_DIR / filename))
        return filename, communities

    def generate_community_subgraph(G, communities, comm_id, spender_ids, receiver_ids):
        net = Network(height="900px", width="100%", directed=True, notebook=False)
        
        # Get community members
        members = [n for n, c in communities.items() if c == comm_id]
        
        # Add nodes with highlighting for top spenders/receivers
        top_both = set(str(x) for x in spender_ids) & set(str(x) for x in receiver_ids)
        top_spenders_only = set(str(x) for x in spender_ids) - top_both
        top_receivers_only = set(str(x) for x in receiver_ids) - top_both
        
        for node in members:
            title = f"Node {node}\nCommunity: {comm_id}"
            color = "#8884d8"  # Default community color
            
            if node in top_both:
                color = TOP_BOTH_COLOR
                title += "\nTop Spender & Receiver"
            elif node in top_spenders_only:
                color = TOP_SPENDER_COLOR
                title += "\nTop Spender"
            elif node in top_receivers_only:
                color = TOP_RECEIVER_COLOR
                title += "\nTop Receiver"
            
            net.add_node(node, label=node, color=color, title=title, size=15)
        
        # Add edges within community
        for src, dst, data in G.edges(data=True):
            if src in members and dst in members:
                net.add_edge(src, dst, 
                            title=f"From: {src}\nTo: {dst}\nValue: {data['weight']:,} SAT\n≈ ${data['usd']:,.2f} USD",
                            arrows='to')
        
        filename = f"community_{comm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
        net.save_graph(str(GENERATED_DIR / filename))
        return filename, communities

    def generate_comparison_network(graph_df, spender_ids, receiver_ids, communities, index, change_data=None):
        if graph_df is None or graph_df.is_empty():
            return None
            
        net = Network(height="700px", width="100%", directed=True, notebook=False)
        
        top_both = set(str(x) for x in spender_ids) & set(str(x) for x in receiver_ids)
        top_spenders_only = set(str(x) for x in spender_ids) - top_both
        top_receivers_only = set(str(x) for x in receiver_ids) - top_both
        
        node_list = set(graph_df["SRC_ID"].cast(str)).union(set(graph_df["DST_ID"].cast(str)))
        for node in node_list:
            color = "#cccccc"  # Default color
            node_class = ""  # Initialize node_class
            
            # Only apply special coloring for the second graph (index == 2)
            if index == 2 and change_data:
                if node in change_data['common_nodes']:
                    color = "#000000"
                    node_class = "common-node"
                elif node in change_data['new_nodes']:
                    color = '#FF851B'
                elif node in change_data['disappeared_nodes']:
                    color = '#FF4136'
            
            # Handle top nodes (applies to both graphs)
            if node in top_both:
                color = TOP_BOTH_COLOR
            elif node in top_spenders_only:
                color = TOP_SPENDER_COLOR
            elif node in top_receivers_only:
                color = TOP_RECEIVER_COLOR
            
            comm = communities.get(node, '')
            net.add_node(node, label=node, color=color, 
                    title=f"Node {node}\nCommunity: {comm}", size=15, 
                    className=node_class)

        for row in graph_df.rows():
            src, dst, satoshi, usd = row
            comm_src = communities.get(str(src), '')
            comm_dst = communities.get(str(dst), '')
            net.add_edge(str(src), str(dst), 
                        title=f"From: {src} ({comm_src})\nTo: {dst} ({comm_dst})\nValue: {satoshi:,} SAT\n≈ ${usd:,.2f} USD",
                        arrows='to')

        filename = f"compare_network_{index}_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
        net.save_graph(str(GENERATED_DIR / filename))
        return filename

    @app.route('/search-transactions', methods=['POST'])
    def search_transactions():
        data = request.json
        date_str = data.get('date')
        hour = int(data.get('hour'))
        search_type = data.get('search_type')
        
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            _, graph_df = load_hour_data(date_obj, hour)
            
            if graph_df is None or graph_df.is_empty():
                return jsonify({"error": "No graph data available for search"}), 404
            
            G = nx.DiGraph()
            for row in graph_df.rows():
                src, dst, satoshi, usd = row
                G.add_edge(str(src), str(dst), weight=satoshi, usd=usd)
            
            undirected = G.to_undirected()
            numeric_communities = community_louvain.best_partition(undirected)
            communities = name_communities(numeric_communities)
            
            results = []
            if search_type == 'node-to-node':
                from_node = str(data.get('from_node'))
                to_node = str(data.get('to_node'))
                filtered = graph_df.filter(
                    (pl.col("SRC_ID").cast(str) == from_node) & 
                    (pl.col("DST_ID").cast(str) == to_node))
            elif search_type == 'node-to-comm':
                from_node = str(data.get('from_node'))
                to_comm = data.get('to_comm')
                members = [n for n, c in communities.items() if c == to_comm]
                filtered = graph_df.filter(
                    (pl.col("SRC_ID").cast(str) == from_node) & 
                    (pl.col("DST_ID").cast(str).is_in(members)))
            elif search_type == 'node-to-all':
                from_node = str(data.get('from_node'))
                filtered = graph_df.filter(pl.col("SRC_ID").cast(str) == from_node)
            elif search_type == 'comm-to-node':
                from_comm = data.get('from_comm')
                to_node = str(data.get('to_node'))
                members = [n for n, c in communities.items() if c == from_comm]
                filtered = graph_df.filter(
                    (pl.col("SRC_ID").cast(str).is_in(members)) & 
                    (pl.col("DST_ID").cast(str) == to_node))
            elif search_type == 'comm-to-all':
                from_comm = data.get('from_comm')
                members = [n for n, c in communities.items() if c == from_comm]
                filtered = graph_df.filter(pl.col("SRC_ID").cast(str).is_in(members))
            else:
                return jsonify({"error": "Invalid search type"}), 400
            
            for row in filtered.rows():
                src, dst, satoshi, usd = row
                results.append({
                    'src': str(src),
                    'dst': str(dst),
                    'satoshi': satoshi,
                    'usd': usd,
                    'src_comm': communities.get(str(src), ''),
                    'dst_comm': communities.get(str(dst), '')
                })
                
            return jsonify({
                "results": results,
                "message": f"Found {len(results)} transactions"
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/section3", methods=["GET", "POST"])
    def home_section3():
        return render_template('section3/index.html')

    @app.route("/single", methods=["GET", "POST"])
    def single_view():
        error = None
        hour_stats = None
        graph_stats = None
        node_transactions = None
        network_file = None
        spenders = None
        receivers = None
        communities = None
        top_comm_spenders = None
        top_comm_receivers = None
        community_view = request.form.get("community_view", "false") == "true"
        search_query = request.form.get("search", "")
        selected_date = request.form.get("date", "")
        selected_hour = request.form.get("hour", "")
        
        if request.method == "POST":
            try:
                date_str = request.form["date"]
                hour = int(request.form["hour"])
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                validate_date(date_obj)
                
                full_df, graph_df = load_hour_data(date_obj, hour)
                
                if full_df is None or full_df.is_empty():
                    raise ValueError("No data found for selected date/hour")
                
                hour_stats, graph_stats, _ = calculate_stats(full_df, graph_df)
                spenders, receivers = analyze_money_flow(full_df)
                spender_ids = [str(s["SRC_ID"]) for s in (spenders or [])]
                receiver_ids = [str(r["DST_ID"]) for r in (receivers or [])]
                
                if graph_df is not None and not graph_df.is_empty():
                    G = nx.DiGraph()
                    for row in graph_df.rows():
                        src, dst, satoshi, usd = row
                        G.add_edge(str(src), str(dst))
                    
                    undirected = G.to_undirected()
                    numeric_communities = community_louvain.best_partition(undirected)
                    communities = name_communities(numeric_communities)
                    
                    top_comm_spenders, top_comm_receivers = get_top_communities(graph_df, communities)
                    
                    if search_query:
                        network_file, _ = generate_network(
                            graph_df, 
                            spender_ids, 
                            receiver_ids,
                            community_view,
                            search_query,
                            communities
                        )
                    else:
                        network_file, _ = generate_network(
                            graph_df, 
                            spender_ids, 
                            receiver_ids,
                            community_view,
                            None,
                            communities
                        )
                    
                    node_transactions = []
                    for row in graph_df.rows():
                        src, dst, satoshi, usd = row
                        node_transactions.append({
                            'src': str(src),
                            'dst': str(dst),
                            'satoshi': satoshi,
                            'usd': usd,
                            'src_comm': communities.get(str(src), ''),
                            'dst_comm': communities.get(str(dst), '')
                        })
                else:
                    raise ValueError("No transactions available for visualization")
                
            except Exception as e:
                error = str(e)
        
        return render_template("section3/single.html",
                            network_file=network_file,
                            hour_stats=hour_stats,
                            graph_stats=graph_stats,
                            node_transactions=node_transactions,
                            spenders=spenders,
                            receivers=receivers,
                            communities=communities,
                            top_comm_spenders=top_comm_spenders,
                            top_comm_receivers=top_comm_receivers,
                            community_view=community_view,
                            min_date=MIN_DATE.strftime("%Y-%m-%d"),
                            max_date=MAX_DATE.strftime("%Y-%m-%d"),
                            error=error,
                            search_query=search_query,
                            selected_date=selected_date,
                            selected_hour=selected_hour)

    @app.route("/compare", methods=["GET", "POST"])
    def compare_view():
        error = None
        comparison_data = []
        selected_dates = [None, None]
        selected_hours = [None, None]
        change_data = None
        growth_metrics = None

        if request.method == "POST":
            try:
                graph_dfs = []
                for i in range(2):
                    date_str = request.form[f"date{i+1}"]
                    hour = int(request.form[f"hour{i+1}"])
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    validate_date(date_obj)
                    
                    full_df, graph_df = load_hour_data(date_obj, hour)
                    graph_dfs.append(graph_df)
                    
                    if full_df is None or full_df.is_empty():
                        raise ValueError(f"No data found for selection {i+1}")
                    
                    hour_stats, graph_stats, _ = calculate_stats(full_df, graph_df)
                    spenders, receivers = analyze_money_flow(full_df)
                    spender_ids = [str(s["SRC_ID"]) for s in (spenders or [])]
                    receiver_ids = [str(r["DST_ID"]) for r in (receivers or [])]
                    
                    G = nx.DiGraph()
                    for row in graph_df.rows():
                        src, dst, satoshi, usd = row
                        G.add_edge(str(src), str(dst))
                    
                    undirected = G.to_undirected()
                    numeric_communities = community_louvain.best_partition(undirected)
                    communities = name_communities(numeric_communities)
                    
                    metrics, bridge_nodes = analyze_topology(graph_df, communities)
                    community_sizes = get_community_sizes(communities)
                    balances = calculate_node_balances(graph_df)
                    top_comm_spenders, top_comm_receivers = get_top_communities(graph_df, communities)
                    
                    transactions = None
                    if graph_df is not None and not graph_df.is_empty():
                        transactions = graph_df.with_columns(
                            pl.col("SRC_ID").cast(str).replace(communities).alias("SRC_Community"),
                            pl.col("DST_ID").cast(str).replace(communities).alias("DST_Community")
                        ).rows(named=True)
                    
                    comparison_data.append({
                        'network_file': None,
                        'hour_stats': hour_stats,
                        'graph_stats': graph_stats,
                        'spenders': spenders,
                        'receivers': receivers,
                        'transactions': transactions,
                        'communities': communities,
                        'community_sizes': community_sizes,
                        'top_comm_spenders': top_comm_spenders,
                        'top_comm_receivers': top_comm_receivers,
                        'metrics': metrics,
                        'bridge_nodes': list(bridge_nodes),
                        'selected_date': date_str,
                        'selected_hour': f"{hour:02d}:00",
                        'node_balances': balances
                    })
                    
                    selected_dates[i] = date_str
                    selected_hours[i] = f"{hour:02d}:00"

                if len(graph_dfs) == 2:
                    raw_change_data = detect_changes(graph_dfs[0], graph_dfs[1])
                    change_data = {
                        'new_nodes': list(raw_change_data['new_nodes']),
                        'disappeared_nodes': list(raw_change_data['disappeared_nodes']),
                        'common_nodes': list(raw_change_data['common_nodes']),
                        'new_edges': [tuple(e) for e in raw_change_data['new_edges']],
                        'disappeared_edges': [tuple(e) for e in raw_change_data['disappeared_edges']],
                        'common_edges': [tuple(e) for e in raw_change_data['common_edges']]
                    }
                    
                    growth_metrics = {
                        'node_growth': len(change_data['new_nodes']) - len(change_data['disappeared_nodes']),
                        'edge_growth': len(change_data['new_edges']) - len(change_data['disappeared_edges']),
                        'value_growth': comparison_data[1]['hour_stats']['total_satoshi'] - comparison_data[0]['hour_stats']['total_satoshi']
                    }

                    for i in range(2):
                        comparison_data[i]['network_file'] = generate_comparison_network(
                            graph_dfs[i],
                            [str(s["SRC_ID"]) for s in (comparison_data[i]['spenders'] or [])],
                            [str(r["DST_ID"]) for r in (comparison_data[i]['receivers'] or [])],
                            comparison_data[i]['communities'],
                            i+1,
                            change_data if i == 1 else None
                        )
                
            except Exception as e:
                error = str(e)
                comparison_data = []
        
        return render_template("section3/compare.html",
                            comparison_data=comparison_data or [],
                            selected_dates=selected_dates,
                            selected_hours=selected_hours,
                            min_date=MIN_DATE.strftime("%Y-%m-%d"),
                            max_date=MAX_DATE.strftime("%Y-%m-%d"),
                            error=error,
                            change_data=change_data or {},
                            growth_metrics=growth_metrics or {})

    @app.route('/network/<filename>')
    def serve_network(filename):
        return send_from_directory(GENERATED_DIR, filename)

    @app.route('/community/<filename>')
    def serve_community(filename):
        return send_from_directory(GENERATED_DIR, filename)

    def cleanup_old_files(max_age_hours=24):
        now = time.time()
        for filepath in GENERATED_DIR.glob('section3/*.html'):
            if filepath.stat().st_mtime < now - max_age_hours * 3600:
                try:
                    filepath.unlink()
                except Exception as e:
                    print(f"Error deleting file {filepath}: {e}")

    if __name__ == "__main__":
        cleanup_old_files()