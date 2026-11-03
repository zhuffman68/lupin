"""Bounded two-dimensional colour components for native UI geometry only."""
import numpy as np


def colour_components(mask, *, max_runs=65_536):
    """Connect neighbouring runs; unrelated scenery cannot join distant controls.

    One-pixel gaps allow native antialiasing. Excessively fragmented captures
    fail closed instead of building an unbounded Python object graph.
    """
    parents=[];boxes=[];previous=[];last_y=-2;count=0
    def root(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]];index=parents[index]
        return index
    for y in np.flatnonzero(mask.any(1)):
        y=int(y)
        if y!=last_y+1:previous=[]
        columns=np.flatnonzero(mask[y])
        edges=np.flatnonzero(np.diff(columns)>2)
        starts=np.r_[0,edges+1];ends=np.r_[edges,len(columns)-1]
        current=[]
        for start,end in zip(starts,ends):
            count+=1
            if count>max_runs:return []
            left,right=int(columns[start]),int(columns[end])
            touching={root(index) for a,b,index in previous if left<=b+1 and a<=right+1}
            if touching:
                index=min(touching)
                for other in touching:
                    if other==index:continue
                    parents[other]=index;a,b,c,d=boxes[other];x,t,z,u=boxes[index]
                    boxes[index]=[min(a,x),min(b,t),max(c,z),max(d,u)]
                x,t,z,u=boxes[index];boxes[index]=[min(x,left),min(t,y),max(z,right),max(u,y)]
            else:index=len(parents);parents.append(index);boxes.append([left,y,right,y])
            current.append((left,right,index))
        previous=current;last_y=y
    return [box for index,box in enumerate(boxes) if root(index)==index]
