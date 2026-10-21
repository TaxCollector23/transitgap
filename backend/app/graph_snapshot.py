"""Lossless, bounded JSON blocks for NetworkX MultiDiGraph snapshots.

Only plain data is decoded. Every node, directed edge key, attribute and WKT
geometry survives; the A* lower bound is recalculated from the actual edges.
"""
import gzip
import sys

import networkx as nx
import numpy as np
import orjson

BLOCK_SIZE = 4096


def write_blocks(graph, path):
    def encode(value):
        if hasattr(value, 'wkt'):
            return value.wkt
        if hasattr(value, 'item'):
            return value.item()
        return str(value)
    temporary = path.with_suffix(path.suffix + '.part')
    with gzip.open(temporary, 'wb', compresslevel=6) as output:
        output.write(orjson.dumps({'format':'transitgap-graph/2','attributes':graph.graph},default=encode)+b'\n')
        for kind, rows in (('nodes', graph.nodes(data=True)), ('edges', graph.edges(keys=True,data=True))):
            block=[]
            for row in rows:
                block.append(row)
                if len(block)==BLOCK_SIZE:
                    output.write(orjson.dumps([kind,block],default=encode)+b'\n')
                    block=[]
            if block:
                output.write(orjson.dumps([kind,block],default=encode)+b'\n')
    temporary.replace(path)


def read_blocks(source, header):
    graph=nx.MultiDiGraph()
    graph.graph.update(header['attributes'])
    canonical={}
    scale=1.0
    def share(attributes):
        # orjson shares attribute keys; interning values also shares reciprocal
        # geometry/name strings without changing their contents or direction.
        for key,value in attributes.items():
            if isinstance(value,str):
                attributes[key]=sys.intern(value)
        return attributes
    for line in source:
        kind,rows=orjson.loads(line)
        if kind=='nodes':
            for node,attrs in rows:
                canonical[node]=node
                graph._node[node]=share(attrs)
                graph._succ[node]={}
                graph._pred[node]={}
        elif kind=='edges':
            # NetworkX 3.x MultiDiGraph storage adapter. Successor/predecessor
            # maps MUST share the same key dictionary, exactly as add_edge does.
            # Nodes are already validated by canonical lookup. No edge or tag
            # is filtered. Tests exercise reverse views, parallel keys, mutation
            # and every routing algorithm after restoring this representation.
            for u,v,key,attrs in rows:
                u,v=canonical[u],canonical[v]
                keys=graph._succ[u].get(v)
                if keys is None:
                    keys={}
                    graph._succ[u][v]=keys
                    graph._pred[v][u]=keys
                if key in keys:
                    raise ValueError('Duplicate directed edge key in graph snapshot')
                keys[key]=share(attrs)
            if scale:
                try:
                    values=np.asarray([(graph.nodes[u]['y'],graph.nodes[u]['x'],graph.nodes[v]['y'],graph.nodes[v]['x'],attrs['length']) for u,v,_,attrs in rows],dtype=np.float64)
                    values[:,:4]=np.radians(values[:,:4])
                    lat1,lon1,lat2,lon2,length=values.T
                    h=np.sin((lat2-lat1)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
                    chord=2*6371000*np.arcsin(np.sqrt(np.clip(h,0,1)))
                    if not np.all(np.isfinite(values)) or np.any(length<0):
                        scale=0.0
                    elif np.any(chord>0):
                        scale=min(scale,float(np.min(length[chord>0]/chord[chord>0])))
                except (KeyError,ValueError,TypeError):
                    scale=0.0
        else:
            raise ValueError('Unknown graph snapshot block')
    # Conservative slack covers vectorized/scalar floating-point differences.
    graph.graph['transitgap_heuristic_scale']=max(0.0,scale*(1-1e-10))
    return graph
