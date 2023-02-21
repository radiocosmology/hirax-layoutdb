"""
structure.py

Contains methods for storing clientside interface information.
"""
import time
import re
from unicodedata import name

import warnings
from xmlrpc.client import boolean
from attr import attr, attributes

from gremlin_python.process.traversal import Order, P, TextP
from sympy import true
from graph_connection import g
from gremlin_python.process.graph_traversal import __, constant

from exceptions import *

from typing import Optional, List

# A placeholder value for the end_time attribute for a
# relation that is still ongoing.
EXISTING_RELATION_END_PLACEHOLDER = 2**63 - 1

# A placeholder value for the end_edit_time attribute for a relation
# that is still ongoing.
EXISTING_RELATION_END_EDIT_PLACEHOLDER = -1

# Placeholder for the ID of an element that does not exist serverside.
VIRTUAL_ID_PLACEHOLDER = -1

_vertex_cache = dict()


class Element:
    """
    The simplest element. Contains an ID.
    :ivar id: The unique identifier of the element. 

    If id is VIRTUAL_ID_PLACEHOLDER, then the 
    element is not in the actual graph and only exists clienside.
    """

    _id: int

    def __init__(self, id: int):
        """
        Initialize the Element.

        :param id: ID of the element.
        :type id: int
        """

        self._set_id(id)

    def _set_id(self, id: int):
        """Set the _id attribute of this Element to :param id:.

        :param id: ID of the element.
        :type id: int
        """

        self._id = id

    def id(self):
        """Return the ID of the element.
        """

        return self._id

    def added_to_db(self) -> bool:
        """Return whether this element is added to the database,
        that is, whether the ID is not the virtual ID placeholder.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return self._id != VIRTUAL_ID_PLACEHOLDER


class Vertex(Element):
    """
    The representation of a vertex. Can contain attributes.

    :ivar category: The category of the Vertex.
    :ivar time_added: When this vertex was added to the database (UNIX time).
    :ivar time_disabled: When this vertex was disabled in the database (UNIX time).
    :ivar active: Whether the vertex is disabled or not.
    :ivar replacement: If the vertex has been replaced, then this property points towards the vertex that replaced it.
    """

    category: str
    time_added: int
    time_disabled: int
    active: bool
    replacement: int

    def __init__(self, id: int):
        """
        Initialize the Vertex.

        :param id: ID of the Vertex.
        :type id: int

        :param category: The category of the Vertex.
        :type category: str

        :param edges: The list of Edge instances that are 
        connected to the Vertex.
        :type edges: List[Edge]
        """

        Element.__init__(self, id)

    def add(self, attributes: dict):
        """
        Add the vertex of category self.category
        to the JanusGraph DB along with attributes from :param attributes:.

        :param attributes: A dictionary of attributes to attach to the vertex.
        :type attributes: dict
        """

        # If already added.
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"Vertex already exists in the database."
            )

        else:

            # set time added to now.
            self.time_added = int(time.time())

            self.active = True

            self.replacement = 0

            self.time_disabled = EXISTING_RELATION_END_EDIT_PLACEHOLDER

            traversal = g.addV().property('category', self.category) \
                         .property('time_added', self.time_added) \
                         .property('time_disabled', self.time_disabled) \
                         .property('active', self.active) \
                         .property('replacement', self.replacement)

            for key in attributes:

                if isinstance(attributes[key], list):
                    for val in attributes[key]:
                        traversal = traversal.property(key, val)

                else:
                    traversal = traversal.property(key, attributes[key])

            v = traversal.next()

            # this is NOT the id of a Vertex instance,
            # but rather the id of the GremlinPython vertex returned
            # by the traversal.
            self._set_id(v.id)

            Vertex._cache_vertex(self)

    def replace(self, id):
        """Replaces the vertex in the JanusGraph DB with the new vertex by changing its property 'active' from true to false and transfering all the edges to the new vertex. The old vertex contains the ID of the new vertex as an attribute.

        :param id: ID of the new Vertex.
        :type id: int

        """

        # The 'replacement' property now points to the new vertex that replaced the self vertex..
        g.V(self.id()).property('replacement', id).iterate()

        # List of all the properties of the outgoing edges from the self vertex.
        o_edges_values_list = g.V(self.id()).outE().valueMap().toList()

        # List of all the outgoing vertices connected to the self vertex.
        o_vertices_list = g.V(self.id()).out().id_().toList()

        # These edges are not copied when replacing a vertex because these edges
        # are selected by the user while adding a new component version, or a new property type, or a new flag
        # or a new component respectively.
        for i in range(len(o_vertices_list)):

            if o_edges_values_list[i]['category'] == RelationVersionAllowedType.category:
                continue
            if o_edges_values_list[i]['category'] == RelationPropertyAllowedType.category:
                continue
            if o_edges_values_list[i]['category'] == RelationFlagSeverity.category:
                continue
            if o_edges_values_list[i]['category'] == RelationFlagType.category:
                continue
            if o_edges_values_list[i]['category'] == RelationComponentType.category:
                continue
            if o_edges_values_list[i]['category'] == RelationVersion.category:
                continue

            # Adds an outgoing edge from the new vertex to the vertices in the list o_vertices_list.
            add_edge_1 = g.V(id).addE(o_edges_values_list[i]['category']).to(__.V().hasId(o_vertices_list[i])).as_(
                'e1').select('e1')

            # Copies all the properties of an outgoing edge and stores them in a list.
            traversal = g.V(self.id()).outE()[i].properties().toList()

            for i2 in range(len(traversal)):
                add_edge_1 = add_edge_1.property(
                    traversal[i2].key, traversal[i2].value)

                if i2 == (len(traversal)-1):
                    add_edge_1 = add_edge_1.next()

            # After all the properties have been copied from all the edges, the edges of the
            # self vertex are dropped.
            if i == (len(o_vertices_list)-1):
                g.V(self.id()).outE().drop().iterate()

        i_edges_values_list = g.V(self.id()).inE().valueMap().toList()
        i_vertices_list = g.V(self.id()).in_().id_().toList()

        for j in range(len(i_vertices_list)):

            add_edge_2 = g.V(id).addE(i_edges_values_list[j]['category']).from_(__.V().hasId(
                i_vertices_list[j])).as_('e2').select('e2')

            traversal = g.V(self.id()).inE()[j].properties().toList()

            for j2 in range(len(traversal)):
                add_edge_2 = add_edge_2.property(
                    traversal[j2].key, traversal[j2].value)

                if j2 == (len(traversal)-1):
                    add_edge_2 = add_edge_2.next()

            if j == (len(i_vertices_list)-1):
                g.V(self.id()).inE().drop().iterate()

    def disable(self, disable_time: int = int(time.time())):
        """Disables the vertex as well all the edges connected to the vertex by setting the property from 'active' from true to false.

        :ivar disable_time: When this vertex was disabled in the database (UNIX time).

        """

        # Sets the active property from true to false and registers the time when
        # this self vertex was disabled.
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Counts the total number of edges connected to this vertex.
        edge_count = g.V(self.id()).bothE().toList()

        # Disables all the conencted edges.
        for i in range(len(edge_count)):
            g.V(self.id()).bothE()[i].property('active', False).property(
                'time_disabled', disable_time).next()

    def added_to_db(self) -> bool:
        """Return whether this vertex is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform 
        a query to the database to determine if the vertex 
        has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or
            g.V(self.id()).count().next() > 0
        )

    def _in_vertex_cache(self) -> bool:
        """Return whether this vertex ID is in the vertex cache.

        :return: True if vertex ID is in _vertex_cache, false otherwise.
        :rtype: bool
        """

        return self.id() in _vertex_cache

    @classmethod
    def _cache_vertex(cls, vertex):
        """Add a vertex and its ID to the vertex cache if not already added,
        and return this new cached vertex. 

        TODO: Raise an error if already cached, because that'd mean there's
        an implementation error with the caching.
        """

        if vertex.id() not in _vertex_cache:

            if not vertex.added_to_db():

                # Do nothing?

                return

            _vertex_cache[vertex.id()] = vertex

        return _vertex_cache[vertex.id()]


class Edge(Element):
    """
    The representation of an edge connecting two Vertex instances.

    :ivar inVertex: The Vertex instance that the Edge is going into.
    :ivar outVertex: The Vertex instance that the Edge is going out of.
    :ivar category: The category of the Edge.
    :ivar time_added: When this edge was added to the database (UNIX time).
    :ivar time_disabled: When this edge was disabled in the database (UNIX time).
    :ivar active: Whether the edge is disabled or not.
    :ivar replacement: If the edge has been replaced, then this property points towards the edge that replaced it.
    """

    inVertex: Vertex
    outVertex: Vertex

    category: str
    time_added: int
    time_disabled: int
    active: bool
    replacement: int

    def __init__(
        self, id: int, inVertex: Vertex, outVertex: Vertex
    ):
        """
        Initialize the Edge.

        :param id: ID of the Edge.
        :type id: int

        :param inVertex: A Vertex instance that the Edge will go into.
        :type inVertex: Vertex

        :param outVertex: A Vertex instance that the Edge will go out of.
        :type outNote: Vertex

        :param outVertex: A Vertex instance that the Edge will go out of.
        :type outNote: Vertex

        :param category: The category of the Edge
        :type category: str
        """

        Element.__init__(self, id)

        self.inVertex = inVertex
        self.outVertex = outVertex

    def add(self, attributes: dict):
        """Add an edge between two vertices in JanusGraph.

        :param attributes: Attributes to add to the edge. Must have string
        keys and corresponding values.
        :type attributes: dict
        """

        if not self.inVertex.added_to_db():
            self.inVertex.add()

        if not self.outVertex.added_to_db():
            self.outVertex.add()

        if self.added_to_db():
            raise EdgeAlreadyAddedError(
                f"Edge already exists in the database."
            )

        else:

            # set time added to now.
            self.time_added = int(time.time())

            self.active = True

            self.replacement = 0

            self.time_disabled = EXISTING_RELATION_END_EDIT_PLACEHOLDER

            traversal = g.V(self.outVertex.id()).addE(self.category) \
                .to(__.V(self.inVertex.id())) \
                .property('category', self.category).property('time_added', self.time_added).property(
                'time_disabled', self.time_disabled).property('active', self.active).property('replacement', self.replacement)

            for key in attributes:
                traversal = traversal.property(key, attributes[key])

            e = traversal.next()

            self._set_id(e.id)

    def added_to_db(self) -> bool:
        """Return whether this edge is added to the database,
        that is, whether the ID is not the virtual ID placeholder, and perform a
        query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or
            g.E(self.id()).count().next() > 0
        )

class Timestamp:
    """A timestamp for starting or ending connections, properties, etc.
    :ivar time: The time of the timestamp, in UNIX time.
    :ivar uid: The user who made the timestamp. (Can be an integer, not a
               string).
    :ivar edit_time: The time of when the timestamp was created, in UNIX time.
    :ivar comments: Any comments about this timestamp.
    """
    time: float
    uid: str
    edit_time: float
    comments: str

    def __init__(self, time, uid, edit_time, comments=""):
        self.time = time
        self.uid = uid
        self.edit_time = edit_time
        self.comments = comments

    def as_dict(self):
        return {
            "time": self.time,
            "uid": self.uid,
            "edit_time": self.edit_time,
            "comments": self.comments
        }


class TimestampedEdge(Edge):
    """An edge that has a timestamp."""
    """Representation of a "rel_connection" edge.

    :ivar start: The starting timestamp, as a `Timestamp` instance.
    :ivar end: The ending timestamp, as a `Timestamp` instance.
    """

    start: Timestamp
    end: Timestamp

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex, start: Timestamp,
        end: Timestamp = None, id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """Initialize the connection.

        :param inVertex: The Vertex that the edge is going into.
        :type inVertex: Vertex
        :param outVertex: The Vertex that the edge is going out of.
        :type outVertex: Vertex
        :param start: The starting timestamp.
        :type start: Timestamp
        :param end: The ending timestamp.
        :type end: Timestamp or None
        """

        self.start = start
        if end:
            self.end = end
        else:
            self.end = Timestamp(EXISTING_RELATION_END_PLACEHOLDER, "",
                                 EXISTING_RELATION_END_EDIT_PLACEHOLDER, "")
        Edge.__init__(self=self, id=id, inVertex=inVertex, outVertex=outVertex)

    def as_dict(self):
        """Return a dictionary representation."""
        return {
            "start": self.start.as_dict(),
            "end": self.end.as_dict()
        }

    def add(self):
        """Add this timestamped edge to the database.
        """

        attributes = {
            "start_time": self.start.time,
            "start_uid": self.start.uid,
            "start_edit_time": self.start.edit_time,
            "start_comments": self.start.comments,
            "end_time": self.end.time,
            "end_uid": self.end.uid,
            "end_edit_time": self.end.edit_time,
            "end_comments": self.end.comments
        }

        Edge.add(self, attributes=attributes)

    def _end(self, end: Timestamp):
        """Set the end timestamp.

        :param end: The ending timestamp of the connection. 
        :type end: Timestamp
        """

        if not self.added_to_db():
            # Edge not added to DB!
            raise EdgeNotAddedError(
                f"Edge between {self.inVertex} and {self.outVertex} " +
                "does not exist in the database."
            )

        self.end = end

        g.E(self.id()).property('end_time', end.time) \
            .property('end_uid', end.uid) \
            .property('end_edit_time', end.edit_time) \
            .property('end_comments', end.comments).iterate()


###############################################################################
#                                   NODES                                     #
###############################################################################

class ComponentType(Vertex):
    """
    The representation of a component type.

    :ivar comments: The comments associated with the component type.
    :ivar name: The name of the component type.
    """

    comments: str
    name: str
    category: str = "component_type"

    def __new__(
        cls, name: str, comments: str = "", id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Return a ComponentType instance given the desired attributes.

        :param name: The name of the component type. 
        :type name: str

        :param comments: The comments attached to the component type, 
        defaults to ""
        :type comments: str  

        :param id: The serverside ID of the ComponentType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
        self, name: str, comments: str = "", id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Initialize the ComponentType vertex with a category, name,
        and comments for self.attributes.

        :param name: The name of the component type. 
        :type name: str

        :param comments: The comments attached to the component type. 
        :type comments: str  
        """

        self.name = name
        self.comments = comments
        Vertex.__init__(self, id=id)

    def as_dict(self):
        """Return a dictionary representation."""
        return {"name": self.name, "comments": self.comments}

    def add(self):
        """Add this ComponentType vertex to the serverside.
        """

        # If already added.
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"ComponentType with name {self.name} " +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments
        }

        Vertex.add(self=self, attributes=attributes)

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the ComponentType vertex in the serverside.

        :param newVertex: The new ComponentType vertex that is replacing the old ComponentType vertex.
        :type newVertex: ComponentType

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1: Sets the property active from true to false and registers the time when the
        # vertex was disabled.
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2: Adds the new vertex in the serverside.
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        # Replaces the ComponentType vertex with the new ComponentType vertex.
        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """Return whether this ComponentType is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform 
        a query to the database to determine if the 
        vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', ComponentType.category)
                .has('name', self.name).has('active', True).count().next() > 0
            )
        )

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a ComponentType instance based on
        component type of name :param name:.

        :param name: The name of the component type.
        :type name: str
        :return: A ComponentType instance with the correct name, comments, and 
        ID.
        :rtype: ComponentType
        """

        try:
            d = g.V().has('active', True) \
                .has('category', ComponentType.category) \
                .has('name', name).as_('v').valueMap().as_('props') \
                .select('v').id_().as_('id').select('props', 'id').next()
        except:
            raise ComponentTypeNotAddedError

        props, id_ = d['props'], d['id']

        Vertex._cache_vertex(
            ComponentType(
                name=name,
                comments=props['comments'][0],
                id=id_
            )
        )

        return _vertex_cache[id_]

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a ComponentType instance based on
        the ID.

        :param id: The serverside ID of the ComponentType vertex.
        :type id: int
        :return: Return a ComponentType from that ID.
        :rtype: ComponentType
        """

        if id not in _vertex_cache:

            d = g.V(id).valueMap().next()

            Vertex._cache_vertex(
                ComponentType(
                    name=d['name'][0],
                    comments=d['comments'][0],
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def _attrs_to_type(cls, name: str, comments: str, id: int):
        """Given name, comments and id of a ComponentType, see if one
        exists in the cache. If so, return the cached ComponentType.
        Otherwise, create a new one, cache it, and return it.

        :param name: The name of the ComponentType vertex
        :type name: str
        :param comments: Comments associated with the ComponentType vertex
        :type comments: str
        :param id: The ID of the ComponentType vertex.
        :type id: int
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                ComponentType(
                    name=name,
                    comments=comments,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_names_of_types_and_versions(cls):
        """
        Return a list of dictionaries, of the format
        {'type': <ctypename>, 'versions': [<revname>, ..., <revname>]}

        where <ctypename> is the name of the component type, and
        the corresponding value of the 'versions' key is a list of the names
        of all of the versions.

        Used for updating the filter panels.

        :return: a list of dictionaries, of the format
        {'type': <ctypename>, 'versions': [<revname>, ..., <revname>]}
        :rtype: list[dict]
        """

        ts = g.V().has('active', True).has('category', ComponentType.category) \
            .order().by('name', Order.asc) \
            .project('name', 'versions') \
            .by(__.values('name')) \
            .by(__.both(RelationVersionAllowedType.category)
                .order().by('name', Order.asc).values('name').fold()
            ).toList()

        return ts

    @classmethod
    def get_list(
        cls,
        range: tuple,
        order_by: str,
        order_direction: str,
        name_substring: str
    ):
        """
        Return a list of ComponentTypes based in the range :param range:,
        based on the name substring in :param name_substring:, 
        and order them based on :param order_by: 
        in the direction :param order_direction:.

        :param range: The range of ComponentTypes to query. If the second
        coordinate is -1, then the range is (range[1], inf)
        :type range: tuple[int, int]

        :param order_by: What to order the component types by. Must be in
        {'name'}
        :type order_by: str

        :param order_direction: Order the component types by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param name_substring: What substring of the name property of the
        component type to filter by.
        :type name_substring: str

        :return: A list of ComponentType instances.
        :rtype: list[ComponentType]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name'}

        traversal = g.V().has('active', True).has('category', ComponentType.category) \
            .has('name', TextP.containing(name_substring))

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        # How to order the component types.
        # This coalesce thing is done to prevent "property does not exist" error
        # not sure why it happens as the 'name' property will ALWAYS exist...
        # but maybe the traversal somehow catches other vertices not of this
        # type...
        if order_by == 'name':
            traversal = traversal.order().by(
                __.coalesce(__.values('name'), constant("")),
                direction
            )

        # Component type query to DB
        cts = traversal.range(range[0], range[1]) \
            .project('id', 'name', 'comments') \
            .by(__.id_()) \
            .by(__.values('name')) \
            .by(__.values('comments')) \
            .toList()

        component_types = []

        for entry in cts:
            id, name, comments = entry['id'], entry['name'], entry['comments']

            component_types.append(
                ComponentType._attrs_to_type(
                    id=id,
                    name=name,
                    comments=comments
                )
            )

        return component_types

    @classmethod
    def get_count(cls, name_substring: str):
        """Return the count of ComponentTypes given a substring of the name
        property.

        :param name_substring: A substring of the name property of the
        ComponentType
        :type name_substring: str

        :return: The number of ComponentTypes that contain 
        :param name_substring: as a substring in the name property.
        :rtype: int
        """

        return g.V().has('active', True).has('category', ComponentType.category) \
            .has('name', TextP.containing(name_substring)) \
            .count().next()


class ComponentVersion(Vertex):
    """
    The representation of a component version.

    :ivar comments: The comments associated with the component type.
    :ivar name: The name of the component type.
    :ivar allowed_type: The ComponentType instance representing the allowed
    type of the component version.
    """

    category: str = "component_version"

    comments: str
    name: str
    allowed_type: ComponentType

    def __new__(
        cls, name: str, allowed_type: ComponentType, comments: str = "",
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Return a ComponentVersion instance given the desired name, comments, 
        allowed type, and id.

        :param name: The name of the component version.
        :type name: str
        :param comments: The comments attached to the component version,
        defaults to ""
        :str comments: str  

        :param allowed_type: The ComponentType instance representing the 
        allowed component type of the version.
        :type allowed_type: ComponentType

        :param id: The serverside ID of the ComponentType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
        self, name: str, allowed_type: ComponentType, comments: str = "",
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Initialize the ComponentVersion vertex.

        :param name: The name of the component version. 
        :param comments: The comments attached to the component version.    
        :param allowed_type: The ComponentType instance representing the 
        allowed component type of the version.
        """

        self.name = name
        self.comments = comments
        self.allowed_type = allowed_type

        Vertex.__init__(self, id=id)

    def as_dict(self):
        """Return a dictionary representation."""
        return {"name": self.name, "comments": self.comments}

    def add(self):
        """Add this ComponentVersion vertex to the serverside.
        """

        # If already added.
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"ComponentVersion with name {self.name} " +
                f"and allowed type {self.allowed_type.name} " +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments
        }

        Vertex.add(self=self, attributes=attributes)

        if not self.allowed_type.added_to_db():
            self.allowed_type.add()

        e = RelationVersionAllowedType(
            inVertex=self.allowed_type,
            outVertex=self
        )

        e.add()

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the ComponentVersion vertex in the serverside.

        :param newVertex: The new ComponentVersion vertex that is replacing the old ComponentVersion vertex.
        :type newVertex: ComponentVersion

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """Return whether this ComponentVersion is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform 
        a query to the database to determine if the vertex 
        has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                self.allowed_type.added_to_db() and
                g.V(self.allowed_type.id())
                .both(RelationVersionAllowedType.category)
                .has('name', self.name).has('active', True).count().next() > 0
            )
        )

    @classmethod
    def _attrs_to_version(
        cls,
        name: str,
        comments: str,
        allowed_type: ComponentType,
        id: int
    ):
        """Given name, comments and id of a ComponentType, see if one
        exists in the cache. If so, return the cached ComponentType.
        Otherwise, create a new one, cache it, and return it.

        :param name: The name of the ComponentType vertex
        :type name: str
        :param comments: Comments associated with the ComponentType vertex
        :type comments: str
        :param id: The ID of the ComponentType vertex.
        :type id: int
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                ComponentVersion(
                    name=name,
                    comments=comments,
                    allowed_type=allowed_type,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_db(cls, name: str, allowed_type: ComponentType):
        """Query the database and return a ComponentVersion instance based on
        component version of name :param name: connected to component type
        :param allowed_type:.

        :param name: The name of the component type.
        :type name: str
        :param allowed_type: The ComponentType instance that this component
        version is to be connected to.
        :type allowed_type: ComponentType
        :return: A ComponentVersion instance with the correct name, comments, 
        allowed component type, and ID.
        :rtype: ComponentVersion
        """

        if allowed_type.added_to_db():

            try:
                d = g.V(allowed_type.id()).has('active', True) \
                    .both(RelationVersionAllowedType.category) \
                    .has('name', name).as_('v').valueMap().as_('attrs') \
                    .select('v').id_().as_('id').select('attrs', 'id').next()
            except StopIteration:
                raise ComponentVersionNotAddedError

            props, id = d['attrs'], d['id']

            Vertex._cache_vertex(
                ComponentVersion(
                    name=name,
                    comments=props['comments'][0],
                    allowed_type=allowed_type,
                    id=id
                )
            )

            return _vertex_cache[id]

        else:
            raise ComponentTypeNotAddedError(
                f"Allowed type {allowed_type.name} of " +
                f"proposed component version {name} has not yet been added " +
                "to the database."
            )

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a ComponentVersion instance based on
        the ID.

        :param id: The serverside ID of the ComponentVersion vertex.
        :type id: int
        :return: Return a ComponentVersion from that ID.
        :rtype: ComponentVersion
        """

        if id not in _vertex_cache:

            d = g.V(id).project('attrs', 'type_id').by(__.valueMap()) \
                .by(__.both(RelationVersionAllowedType.category).id_()).next()

            t = ComponentType.from_id(d['type_id'])

            Vertex._cache_vertex(
                ComponentVersion(
                    name=d['attrs']['name'][0],
                    comments=d['attrs']['comments'][0],
                    allowed_type=t,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_list(
        cls,
        range: tuple,
        order_by: str,
        order_direction: str,
        filters: list
    ):
        """
        Return a list of ComponentVersions in the range :param range:,
        based on the filters in :param filters:,
        and order them based on  :param order_by: in the direction 
        :param order_direction:.

        :param range: The range of ComponentVersions to query
        :type range: tuple[int, int]

        :param order_by: What to order the component versions by. Must be in
        {'name', 'allowed_type'}
        :type order_by: str

        :param order_direction: Order the component versions by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param filters: A list of 2-tuples of the format (name, ctype)
        :type order_by: list

        :return: A list of ComponentVersion instances.
        :rtype: list[ComponentType]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name', 'allowed_type'}

        traversal = g.V().has('active', True).has(
            'category', ComponentVersion.category)

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 2

                contents = []

                # substring of component version name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationVersionAllowedType.category).has(
                            'name',
                            f[1]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        # How to order the component types.
        if order_by == 'name':
            traversal = traversal.order().by('name', direction) \
                .by(
                    __.both(
                        RelationVersionAllowedType.category
                    ).values('name'),
                    Order.asc
            )
        elif order_by == 'allowed_type':
            traversal = traversal.order().by(
                __.both(
                    RelationVersionAllowedType.category
                ).values('name'),
                direction
            ).by('name', Order.asc)

        # Component type query to DB
        cts = traversal.range(range[0], range[1]) \
            .project('id', 'name', 'comments', 'type_id') \
            .by(__.id_()) \
            .by(__.values('name')) \
            .by(__.values('comments')) \
            .by(__.both(RelationVersionAllowedType.category).id_()) \
            .toList()

        component_versions = []

        for entry in cts:
            id, name, comments, type_id = entry['id'], entry['name'], \
                entry['comments'], entry['type_id']

            t = ComponentType.from_id(id=type_id)

            component_versions.append(
                ComponentVersion._attrs_to_version(
                    id=id,
                    name=name,
                    comments=comments,
                    allowed_type=t
                )
            )
        return component_versions

    @classmethod
    def get_count(cls, filters: list):
        """Return the count of ComponentVersions given a list of filters

        :param filters: A list of 2-tuples of the format (name, ctype)
        :type order_by: list

        :return: The number of ComponentVersions that agree with
        :param filters:.
        :rtype: int
        """

        traversal = g.V().has('active', True).has(
            'category', ComponentVersion.category)

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 2

                contents = []

                # substring of component version name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationVersionAllowedType.category).has(
                            'name',
                            f[1]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        return traversal.count().next()


class Component(Vertex):
    """
    The representation of a component. 
    Contains a name attribute, ComponentType instance, can contain a
    ComponentVersion and can contain a Flag

    :ivar name: The name of the component
    :ivar type: The ComponentType instance representing the 
    type of the component.
    :ivar version: Optional ComponentVersion instance representing the
    version of the component.

    """

    category: str = "component"

    name: str
    type: ComponentType
    version: ComponentVersion = None

    def __new__(
        cls, name: str, type: ComponentType,
        version: ComponentVersion = None,
        id: int = VIRTUAL_ID_PLACEHOLDER,
        time_added: int = -1
    ):
        """
        Return a Component instance given the desired name, component type,
        and version.

        :param name: The name of the Component.
        :type name: str

        :param type: The component type of the Component.
        :type type: ComponentType

        :param version: The ComponentVersion instance representing the 
        version of the Component.
        :type version: ComponentVersion

        :param id: The serverside ID of the ComponentType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
        self, name: str, type: ComponentType,
        version: ComponentVersion = None,
        id: int = VIRTUAL_ID_PLACEHOLDER,
        time_added: int = -1
    ):
        """
        Initialize the Component vertex.

        :param name: The name of the component version. 
        :param type: A ComponentType instance representing the type of the
        component.
        :param version: A ComponentVersion instance representing the 
        version of the component, optional.
        """

        self.name = name
        self.type = type
        self.version = version
        self.time_added = time_added

        Vertex.__init__(self, id=id)

    def __str__(self):

        if self.version is None:
            version_text = "no version"

        else:
            version_text = 'version "{self.version.name}"'

        return f'Component of name "{self.name}", \
            type "{self.type.name}", \
            {version_text}, id {self.id()}'

    def add(self):
        """Add this Component to the serverside.
        """

        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"Component with name {self.name} " +
                "already exists in the database."
            )

        attributes = {
            'name': self.name
        }

        Vertex.add(self, attributes)

        if self.version is not None:
            if not self.version.added_to_db():
                self.version.add()

            rev_edge = RelationVersion(
                inVertex=self.version,
                outVertex=self
            )

            rev_edge._add()

        if not self.type.added_to_db():
            self.type.add()

        type_edge = RelationComponentType(
            inVertex=self.type,
            outVertex=self
        )

        type_edge.add()

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the Component vertex in the serverside.

        :param newVertex: The new Component vertex that is replacing the old Component vertex.
        :type newVertex: Component

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def get_property(self, type, time: int):
        """
        Given a property type, get a property of this component active at time
        :param time:. 

        :param type: The type of the property to extract
        :type type: PropertyType
        :param time: The time to check the active property at.
        :type time: int

        :rtype: Property or None
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not type.added_to_db():
            raise PropertyTypeNotAddedError(
                f"Property type {type.name} of component " +
                 "{self.name} " +
                "has not yet been added to the database."
            )

        # list of property vertices of this property type
        # and active at this time
        vs = g.V(self.id()).bothE(RelationProperty.category) \
              .has('active', True) \
              .has('start_time', P.lte(time)) \
              .has('end_time', P.gt(time)).otherV().as_('v') \
              .both(RelationPropertyType.category) \
              .has('name', type.name) \
              .select('v').toList()

        # If no such vertices found
        if len(vs) == 0:
            return None

        # There should be only one!

        assert len(vs) == 1

        return Property.from_id(vs[0].id)

    def get_all_properties(self):
        """Return all properties, along with their edges of this component as
        a tuple of the form (Property, RelationProperty)

        :rtype: tuple[Property, RelationProperty]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        # list of property vertices of this property type
        # and active at this time
        query = g.V(self.id()).bothE(RelationProperty.category).has('active', True) \
            .as_('e').valueMap().as_('edge_props') \
            .select('e').otherV().id_().as_('vertex_id') \
            .select('edge_props', 'vertex_id').toList()

        # Build up the result of format (property vertex, relation)
        result = []

        for q in query:
            prop = Property.from_id(q['vertex_id'])
            edge = RelationProperty(
                inVertex=prop,
                outVertex=self,
                start=Timestamp(
                    q['edge_props']['start_time'],
                    q['edge_props']['start_uid'],
                    q['edge_props']['start_edit_time'],
                    q['edge_props']['start_comments']
                ),
                end=Timestamp(
                    q['edge_props']['end_time'],
                    q['edge_props']['end_uid'],
                    q['edge_props']['end_edit_time'],
                    q['edge_props']['end_comments']
                )
            )
            result.append((prop, edge))

        return result

    def get_all_properties_of_type(
        self, type,
        from_time: int = -1,
        to_time: int = EXISTING_RELATION_END_PLACEHOLDER
    ):
        """
        Given a property type, return all edges that connected them between time
        :param from_time: and to time :param to_time: as a list.

        :param type: The property type of the desired properties to consider.
        :type component: PropertyType
        :param from_time: Lower bound for time range to consider properties, 
        defaults to -1
        :type from_time: int, optional
        :param to_time: Upper bound for time range to consider properties, 
        defaults to EXISTING_RELATION_END_PLACEHOLDER
        :type to_time: int, optional

        :rtype: list[RelationProperty]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not type.added_to_db():
            raise PropertyTypeNotAddedError(
                f"Property type {type.name} of component {self.name} " +
                "has not yet been added to the database."
            )

        edges = g.V(self.id()).bothE(RelationProperty.category) \
                 .has('active', True) \
                 .has('end_edit_time', EXISTING_RELATION_END_EDIT_PLACEHOLDER)

        if to_time < EXISTING_RELATION_END_PLACEHOLDER:
            edges = edges.has('start_time', P.lt(to_time))

        edges = edges.has('end_time', P.gt(from_time)) \
            .as_('e').otherV().as_('v') \
            .both(RelationPropertyType.category) \
            .has('name', type.name) \
            .select('e').order().by(__.values('start_time'), Order.asc) \
            .project('properties', 'id').by(__.valueMap()).by(__.id_()).toList()

        print("Warning: RelationProperty not initialised properly! "\
              "outVertex should not = type but the property vertex …")
        return [RelationProperty(
            inVertex=self, outVertex=type,
            start=Timestamp(
                e['properties']['start_time'],
                e['properties']['start_uid'],
                e['properties']['start_edit_time'],
                e['properties']['start_comments']
            ),
            end=Timestamp(
                e['properties']['end_time'],
                e['properties']['end_uid'],
                e['properties']['end_edit_time'],
                e['properties']['end_comments']
            ),
            id=e['id']['@value']['relationId']  # weird but you have to
        ) for e in edges]

    def get_all_flags(self):
        """Return all flags connected to this component of the form (Flag)

        :rtype: [Flag]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        # list of flag vertices of this flag type and flag severity and active at this time.

        query = g.V(self.id()).bothE(
            RelationFlagComponent.category).has('active', True).otherV().id_().toList()

        # Build up the result of format (flag vertex)
        result = []

        for q in query:
            flag = Flag.from_id(q)
            result.append((flag))

        return result

    def get_all_subcomponents(self):
        """Return all subcomponents connected to this component of the form
        (Component)

        :rtype: [Component]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        query = g.V(self.id()).inE(RelationSubcomponent.category) \
                 .has('active', True).otherV().id_().toList()

        # Build up the result of format (flag vertex)
        result = []

        for q in query:
            subcomponent = Component.from_id(q)
            result.append((subcomponent))

        return result

    def get_all_supercomponents(self):
        """Return all supercomponents connected to this component of the form
        (Component)

        :rtype: [Component]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )
        # Relation as a subcomponent stays the same except now
        # we have outE to distinguish from subcomponents
        query = g.V(self.id()).outE(RelationSubcomponent.category) \
                 .has('active', True).otherV().id_().toList()

        # Build up the result of format (flag vertex)
        result = []

        for q in query:
            supercomponent = Component.from_id(q)
            result.append((supercomponent))

        return result

    def set_property(
        self, property, time: int,
        uid: str, end_time: int = EXISTING_RELATION_END_PLACEHOLDER,
        edit_time: int = int(time.time()), comments="",
        force_property: bool = False
    ):
        """
        Given a property :param property:, MAKE A VIRTUAL COPY of it,
        add it, then connect it to the component self at start time
        :start_time:. Return the Property instance that was added.

        :param property: The property to add
        :type property: Property
        :param time: The time at which the property was added (real time)
        :type time: int
        :param uid: The ID of the user that added the property
        :type uid: str
        :param end_time: The time at which the property was unset
        (real time), defaults to EXISTING_RELATION_END_PLACEHOLDER
        :type time: int, optional
        :param edit_time: The time at which the user made the change,
        defaults to int(time.time())
        :type edit_time: int, optional
        :param comments: Comments to add with property change, defaults to ""
        :type comments: str, optional
        """

        end_edit_time = EXISTING_RELATION_END_EDIT_PLACEHOLDER
        end_uid = ""
        end_comments = ""

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        current_property = self.get_property(
            type=property.type, time=time
        )

        if current_property is not None:
            if current_property.values == property.values:
                raise PropertyIsSameError(
                    "An identical property of type " +
                    f"{property.type.name} for component {self.name} " +
                    f"is already set with values {property.values}."
                )

#            elif current_property.end.time != EXISTING_RELATION_END_PLACEHOLDER:
#                raise PropertyIsSameError(
#                    "Property of type {property.type.name} for component "\
#                    "{self.name} is already set at this time with an end "\
#                    "time after this time."
#                )
            else:
                # end that property.
                self.unset_property(
                    property=current_property,
                    time=time,
                    uid=uid,
                    edit_time=edit_time,
                    comments=comments
                )

        else:

            existing_properties = self.get_all_properties_of_type(
                type=property.type,
                from_time=time
            )

            if len(existing_properties) > 0:
                if force_property:
                    if end_time != EXISTING_RELATION_END_PLACEHOLDER:
                        raise ComponentPropertiesOverlappingError(
                            "Trying to set property of type " +
                            f"{property.type.name} for component " +
                            f"{self.name} " +
                            "before an existing property of the same type " +
                            "but with a specified end time; " +
                            "replace the property instead."
                        )

                    else:
                        end_time = existing_properties[0].start_time
                        end_edit_time = edit_time
                        end_uid = uid
                        end_comments = comments
                else:
                    raise ComponentSetPropertyBeforeExistingPropertyError(
                        "Trying to set property of type " +
                        f"{property.type.name} for component " +
                        f"{self.name} " +
                        "before an existing property of the same type; " +
                        "set 'force_property' parameter to True to bypass."
                    )

        prop_copy = Property(
            values=property.values,
            type=property.type
        )

        prop_copy._add()

        e = RelationProperty(
            inVertex=prop_copy,
            outVertex=self,
            start=Timestamp(time, uid, edit_time, comments),
            end=Timestamp(end_time, end_uid, end_edit_time, end_comments)
        )

        e.add()

        return prop_copy

    def unset_property(
        self, property, time: int, uid: str,
        edit_time: int = int(time.time()), comments=""
    ):
        """
        Given a property that is connected to this component,
        set the "end" attributes of the edge connecting the component and
        the property to indicate that this property has been removed from the
        component.

        :param property: The property vertex connected by an edge to the 
        component vertex.
        :type property: Property

        :param time: The time at which the property was removed (real time). This value has to be provided.
        :type time: int

        :param uid: The user that removed the property
        :type uid: str

        :param edit_time: The time at which the 
        user made the change, defaults to int(time.time())
        :type edit_time: int, optional

        :param comments: Comments about the property removal, defaults to ""
        :type comments: str, optional
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not property.added_to_db():
            raise PropertyNotAddedError(
                f"Property of component {self.name} " +
                f"of values {property.values} being unset " +
                "has not been added to the database."
            )

        # Check to see if the property already has an end time.
        vs = g.V(self.id()).bothE(RelationProperty.category) \
              .has('active', True) \
              .has('start_time', P.lte(time)) \
              .has('end_time', P.gt(time)) \
              .as_('e').valueMap().as_('edge_props').select('e') \
              .otherV().as_('v').both(RelationPropertyType.category) \
              .has('name', property.type.name) \
              .select('edge_props').toList()
        if len(vs) == 0:
            raise PropertyNotAddedError(
                "Property of type {property.type.name} cannot be unset for "\
                "component {this.name} because it has not been set yet."
            )
        assert(len(vs) == 1)
        print(vs[0])
        if vs[0]['end_time'] < EXISTING_RELATION_END_PLACEHOLDER:
            raise PropertyIsSameError(
                f"Property of type {property.type.name} cannot be unset for "\
                f"component {self.name} because it is set at this time and "\
                f"already has an end time."
            )
        print("slkdjflskdjfslkdjfslkdfjslkdjf")

        g.V(property.id()).bothE(RelationProperty.category).as_('e').otherV() \
            .hasId(self.id()).select('e') \
            .has('end_time', EXISTING_RELATION_END_PLACEHOLDER) \
            .property('end_time', time).property('end_uid', uid) \
            .property('end_edit_time', edit_time) \
            .property('end_comments', comments).iterate()

    def replace_property(self, propertyTypeName: str, property, time: int,
                         uid: str, comments=""):
        """Replaces the Component property vertex in the serverside.

        :param propertyTypeName: The name of the property type being replaced.
        :type propertyTypeName: str

        :param property: The new property that is replacing the old property.
        :type property: Property

        :param time: The time at which the property was added (real time)
        :type time: int

        :param uid: The ID of the user that added the property
        :type uid: str

        :param comments: Comments to add with property change, defaults to ""
        :type comments: str, optional

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # id of the property being replaced.
        id = g.V(self.id()).bothE(RelationProperty.category).has('active', True).has('end_edit_time', EXISTING_RELATION_END_EDIT_PLACEHOLDER).otherV().where(
            __.outE().otherV().properties('name').value().is_(propertyTypeName)).id_().next()

        property_vertex = Property.from_id(id)

        property_vertex.disable()

        # Sets a new property
        self.set_property(
            property=property,
            time=time,
            uid=uid,
            comments=comments
        )

    def disable_property(self, propertyTypeName,
                         disable_time: int = int(time.time())):
        """Disables the property in the serverside

        :param propertyTypeName: The name of the property type being replaced.
        :type propertyTypeName: str

        :param disable_time: When this vertex was disabled in the database
            (UNIX time).
        :type disable_time: int

        """

        g.V(self.id()).bothE(RelationProperty.category).has('active', True)\
         .has('end_edit_time', EXISTING_RELATION_END_EDIT_PLACEHOLDER)\
         .where(__.otherV().bothE(RelationPropertyType.category).otherV()\
         .properties('name').value().is_(propertyTypeName))\
         .property('active', False).property('time_disabled', disable_time)\
         .next()

    def connect(
        self, component, time: int, uid: str,
        end_time: int = EXISTING_RELATION_END_PLACEHOLDER,
        edit_time: int = int(time.time()), comments="",
        force_connection: bool = False
    ):
        """Given another Component :param component:,
        connect the two components.

        :param component: Another Component to connect this component to.
        :type component: Component
        :param time: The time at which these components were connected 
        (real time)
        :type time: int
        :param uid: The ID of the user that connected the components
        :type uid: str
        :param end_time: The time at which these components were disconnected
        (real time), defaults to EXISTING_RELATION_END_PLACEHOLDER
        :type time: int, optional
        :param edit_time: The time at which the user made the change,
        defaults to int(time.time())
        :type edit_time: int, optional
        :param comments: Comments to add with the connection, defaults to ""
        :type comments: str, optional
        :param force_connection: If a connection is being added at a time
        before an existing active connection, give it an end time as well,
        defaults to False
        :type force_connection: bool, optional
        """

        end_edit_time = EXISTING_RELATION_END_EDIT_PLACEHOLDER
        end_uid = ""
        end_comments = ""

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet " +
                "been added to the database."
            )

        if self.name == component.name:
            raise ComponentConnectToSelfError(
                f"Trying to connect component {self.name} to itself."
            )

        current_connection = self.get_connection(
            component=component,
            time=time
        )

        if current_connection is not None:

            # Already connected!
            raise ComponentsAlreadyConnectedError(
                f"Components {self.name} and {component.name} " +
                "are already connected."
            )

        else:

            existing_connections = self.get_all_connections_with(
                component=component,
                from_time=time
            )

            if len(existing_connections) > 0:
                if force_connection:
                    if end_time != EXISTING_RELATION_END_PLACEHOLDER:
                        raise ComponentsOverlappingConnectionError(
                            "Trying to connect components " +
                            f"{self.name} and {component.name} " +
                            "before an existing connection but with a " +
                            "specified end time; " +
                            "replace the connection instead."
                        )

                    else:
                        end_time = existing_connections[0].start_time
                        end_edit_time = edit_time
                        end_uid = uid
                        end_comments = comments
                else:
                    raise ComponentsConnectBeforeExistingConnectionError(
                        "Trying to connect components " +
                        f"{self.name} and {component.name} " +
                        "before an existing connection; set 'force_connection' "
                        + "parameter to True to bypass."
                    )

            current_connection = RelationConnection(
                inVertex=self,
                outVertex=component,
                start=Timestamp(time, uid, edit_time, comments),
                end=Timestamp(end_time, end_uid, end_edit_time, end_comments)
            )

            current_connection.add()

    def disconnect(
        self, component, time: int, uid: str,
        edit_time: int = int(time.time()), comments=""
    ):
        """Given another Component :param component:, disconnect the two
        components at time :param time:.

        :param component: Another Component to disconnect this component from.
        :type component: Component
        :param time: The time at which these components are disconnected
        (real time)
        :type time: int
        :param uid: The ID of the user that disconnected the components
        :type uid: str
        :param edit_time: The time at which the user made the change,
        defaults to int(time.time())
        :type edit_time: int, optional
        :param comments: Comments to add with the disconnection, defaults to ""
        :type comments: str, optional
        """

        # Done for troubleshooting (so you know which component is not added?)

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet " +
                "been added to the database."
            )

        current_connection = self.get_connection(
            component=component,
            time=time
        )

        if current_connection is None:

            # Not connected yet!
            raise ComponentsAlreadyDisconnectedError(
                f"Components {self.name} and {component.name} " +
                "are already disconnected."
            )

        else:
            current_connection._end(Timestamp(time, uid, edit_time, comments))

    def replace_connection(self, otherComponent, time, uid, comments, disable_time: int = int(time.time())):
        """
        Given another Component :param component:,
        replace the existing connection between them.

        :param otherComponent: Another Component that this component has connection with.
        :type othercomponent: Component

        :param time: The time at which these components were connected 
        (real time)
        :type time: int

        :param uid: The ID of the user that connected the components
        :type uid: str

        :param comments: Comments to add with the connection, defaults to ""
        :type comments: str, optional

        :param disable_time: When this edge was disabled in the database (UNIX time).
        :type disable_time: int

        """

        # Disables the current connection.
        g.V(self.id()).bothE(RelationConnection.category).where(
            __.otherV().hasId(otherComponent.id())).property('active', False).property(
            'time_disabled', disable_time).next()

        # Adds the new connection.
        self.connect(
            component=otherComponent, time=time, uid=uid, comments=comments
        )

    def disable_connection(self, otherComponent,
                           disable_time: int = int(time.time())):
        """Disables the connection in the serverside

        :param otherComponent: Another Component that this component has connection with.
        :type othercomponent: Component

        :param disable_time: When this edge was disabled in the database (UNIX time).
        :type disable_time: int    

        """

        g.V(self.id()).bothE(RelationConnection.category).where(
            __.otherV().hasId(otherComponent.id())).property('active', False) \
              .property('time_disabled', disable_time).next()

    def get_all_connections_at_time(
        self, time: int, exclude_subcomponents: bool = False
    ):
        """
        Given a component, return all connections between this Component and 
        all other components.

        :param time: Time to check connections at. 
        :param exclude_subcomponents: If True, then do not return connections
            to subcomponents or supercomponents.

        :rtype: list[RelationConnection/RelationSubcomponent]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        # Build up the result of format (property vertex, relation)
        result = []

        if not exclude_subcomponents:
            # First do subcomponents.
            for q in g.V(self.id()).inE(RelationSubcomponent.category) \
                      .has('active', True).as_('e') \
                      .otherV().id_().as_('vertex_id') \
                      .select('e').id_().as_('edge_id') \
                      .select('vertex_id', 'edge_id').toList():
                c = Component.from_id(q['vertex_id'])
                edge = RelationSubcomponent(
                    inVertex=self,
                    outVertex=c,
                    id=q['edge_id']['@value']['relationId']
                )
                result.append(edge)

            # Now supercomponents.
            for q in g.V(self.id()).outE(RelationSubcomponent.category) \
                      .has('active', True).as_('e') \
                      .otherV().id_().as_('vertex_id') \
                      .select('e').id_().as_('edge_id') \
                      .select('vertex_id', 'edge_id').toList():
                c = Component.from_id(q['vertex_id'])
                edge = RelationSubcomponent(
                    inVertex=c,
                    outVertex=self,
                    id=q['edge_id']['@value']['relationId']
                )
                result.append(edge)

        # List of property vertices of this property type and active at this
        # time
        query = g.V(self.id()).bothE(RelationConnection.category) \
            .has('active', True) \
            .has('start_time', P.lte(time)) \
            .has('end_time', P.gt(time)) \
            .as_('e').valueMap().as_('edge_props') \
            .select('e').otherV().id_().as_('vertex_id') \
            .select('e').id_().as_('edge_id') \
            .select('edge_props', 'vertex_id', 'edge_id').toList()

        for q in query:
            c = Component.from_id(q['vertex_id'])
            edge = RelationConnection(
                inVertex=c,
                outVertex=self,
                start=Timestamp(
                    q['edge_props']['start_time'],
                    q['edge_props']['start_uid'],
                    q['edge_props']['start_edit_time'],
                    q['edge_props']['start_comments']
                ),
                end=Timestamp(
                    q['edge_props']['end_time'],
                    q['edge_props']['end_uid'],
                    q['edge_props']['end_edit_time'],
                    q['edge_props']['end_comments']
                ),
                # weird but you have to
                id=q['edge_id']['@value']['relationId']
            )
            result.append(edge)

        return result

    def get_all_connections_with(
        self, component, from_time: int = -1,
        to_time: int = EXISTING_RELATION_END_PLACEHOLDER
    ):
        """
        Given two components, return all edges that connected them between time
        :param from_time: and to time :param to_time: as a list.

        :param component: The other component to check the connections with.
        :type component: Component
        :param from_time: Lower bound for time range to consider connections, 
        defaults to -1
        :type from_time: int, optional
        :param to_time: Upper bound for time range to consider connections, 
        defaults to EXISTING_RELATION_END_PLACEHOLDER
        :type to_time: int, optional

        :rtype: list[RelationConnection]
        """

        # Done for troubleshooting (so you know which component is not added?)
        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet " +
                "been added to the database."
            )

        edges = g.V(self.id()).bothE(
            RelationConnection.category).has('active', True)

        if to_time < EXISTING_RELATION_END_PLACEHOLDER:
            edges = edges.has('start_time', P.lt(to_time))

        edges = edges.has('end_time', P.gt(from_time)) \
            .as_('e').otherV() \
            .hasId(component.id()).select('e') \
            .order().by(__.values('start_time'), Order.asc) \
            .project('properties', 'id').by(__.valueMap()).by(__.id_()).toList()

        return [RelationConnection(
            inVertex=self, outVertex=component,
            start=Timestamp(
                e['properties']['start_time'],
                e['properties']['start_uid'],
                e['properties']['start_edit_time'],
                e['properties']['start_comments']
            ),
            end=Timestamp(
                e['properties']['end_time'],
                e['properties']['end_uid'],
                e['properties']['end_edit_time'],
                e['properties']['end_comments']
            ),
            id=e['id']['@value']['relationId']  # weird but you have to
        ) for e in edges]

    def get_connection(
        self, component, time: int
    ):
        """Given two components, return the edge that connected them at
        time :param time:.

        :param component: The other component to check the connections with.
        :type component: Component
        :param time: The time to check
        :type time: int
        """

        # Done for troubleshooting (so you know which component is not added?)
        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet " +
                "been added to the database."
            )

        e = g.V(self.id()).bothE(RelationConnection.category).has('active', True) \
            .has('start_time', P.lte(time)) \
            .has('end_time', P.gt(time)) \
            .as_('e').otherV() \
            .hasId(component.id()).select('e') \
            .project('properties', 'id').by(__.valueMap()).by(__.id_()).toList()

        if len(e) == 0:
            return None

        assert len(e) == 1

        return RelationConnection(
            inVertex=self, outVertex=component,
            start=Timestamp(
                e[0]['properties']['start_time'],
                e[0]['properties']['start_uid'],
                e[0]['properties']['start_edit_time'],
                e[0]['properties']['start_comments']
            ),
            end=Timestamp(
                e[0]['properties']['end_time'],
                e[0]['properties']['end_uid'],
                e[0]['properties']['end_edit_time'],
                e[0]['properties']['end_comments']
            ),
            id=e[0]['id']['@value']['relationId']  # weird but you have to
        )

    def get_all_connections(self):
        """Return all connections between this Component and all other
        components, along with their edges of this component as
        a tuple of the form (Component, RelationConnection)

        :rtype: tuple[Component, RelationConnection]
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        # list of property vertices of this property type
        # and active at this time
        query = g.V(self.id()).bothE(RelationConnection.category).has('active', True) \
            .as_('e').valueMap().as_('edge_props') \
            .select('e').otherV().id_().as_('vertex_id') \
            .select('edge_props', 'vertex_id').toList()

        # Build up the result of format (property vertex, relation)
        result = []

        for q in query:
            prop = Component.from_id(q['vertex_id'])
            edge = RelationConnection(
                inVertex=prop,
                outVertex=self,
                start=Timestamp(
                    q['edge_props']['start_time'],
                    q['edge_props']['start_uid'],
                    q['edge_props']['start_edit_time'],
                    q['edge_props']['start_comments']
                ),
                end=Timestamp(
                    q['edge_props']['end_time'],
                    q['edge_props']['end_uid'],
                    q['edge_props']['end_edit_time'],
                    q['edge_props']['end_comments']
                )
            )
            result.append((prop, edge))

        return result

    def subcomponent_connect(
            self, component):
        """
        Given another Component :param component:, make it a subcomponent of the current component.

        :param component: Another component that is a subcomponent of the current component.
        :type component: Component
        """

        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet" +
                "been added to the database."
            )

        if self.name == component.name:
            raise ComponentSubcomponentToSelfError(
                f"Trying to make {self.name} subcomponent to itself."
            )

        current_subcomponent = self.get_subcomponent(
            component=component
        )

        component_to_subcomponent = component.get_subcomponent(
            component=self
        )

        if component_to_subcomponent is not None:
            raise ComponentIsSubcomponentOfOtherComponentError(
                f"Component {component.name} is already a subcomponent of {self.name}"
            )

        if current_subcomponent is not None:

            # Already a subcomponent!
            raise ComponentAlreadySubcomponentError(
                f"component {component.name} is already a subcomponent of component {self.name}"
            )

        else:
            current_subcomponent = RelationSubcomponent(
                inVertex=self,
                outVertex=component
            )

            current_subcomponent.add()

    def get_subcomponent(self, component):
        """Given the component itself and its subcomponent, return the edge between them.

        :param component: The other component which is the subcomponent of the current component.
        :type component: Component
        """

        # Done for troubleshooting (so you know which component is not added?)
        if not self.added_to_db():
            raise ComponentNotAddedError(
                f"Component {self.name} has not yet been added to the database."
            )

        if not component.added_to_db():
            raise ComponentNotAddedError(
                f"Component {component.name} has not yet" +
                "been added to the database."
            )

        e = g.V(self.id()).bothE(RelationSubcomponent.category).has('active', True).as_('e').otherV().hasId(
            component.id()).select('e').project('id').by(__.id_()).toList()

        if len(e) == 0:
            return None

        assert len(e) == 1

        return RelationSubcomponent(
            inVertex=self, outVertex=component,
            id=e[0]['id']['@value']['relationId']
        )

    def disable_subcomponent(self, otherComponent, disable_time: int = int(time.time())):
        """Disabling an edge for a subcomponent

        :param otherComponent: Another Component that this component has connection 'rel_subcomponent' with.
        :type othercomponent: Component

        :param disable_time: When this edge was disabled in the database (UNIX time).
        :type disable_time: int

        """

        g.V(self.id()).bothE(RelationSubcomponent.category).where(
            __.otherV().hasId(otherComponent.id())).property('active', False).property(
            'time_disabled', disable_time).next()

    def added_to_db(self) -> bool:
        """Return whether this Component is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform a 
        query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V()
                .has('category', Component.category)
                .has('name', self.name).has('active', True).count().next() > 0
            )
        )

    @classmethod
    def _attrs_to_component(self, name, id, type_id, rev_ids, time_added):
        """Given the name ID of the component :param id: and the ID of the 
        component type :param type_id: and a list of the IDs of the
        component version vertices :param rev_ids:, 
        create and return a Component based on that.

        :param name: The name of the component
        :type name: str
        :param id: The ID of the component serverside
        :type id: int
        :param type_id: The ID of its component type vertex serverside
        :type type_id: int
        :param rev_ids: A list of IDs of component version vertices serverside
        :type rev_ids: list
        :param time_added: UNIX timestamp of when the Component was added to DB.
        :type time_added: int
        :return: A Component instance corresponding to :param id:, connected
        to the correct ComponentType and ComponentVersion.
        :rtype: Component
        """

        assert len(g.V(id).toList()) == 1

        Vertex._cache_vertex(ComponentType.from_id(type_id))

        crev = None

        if len(rev_ids) > 1:
            raise ValueError(
                f"More than one component version exists for component {name}."
            )

        if len(rev_ids) == 1:
            crev = Vertex._cache_vertex(
                ComponentVersion.from_id(id=rev_ids[0])
            )

        Vertex._cache_vertex(
            Component(
                name=name,
                id=id,
                type=_vertex_cache[type_id],
                version=crev,
                time_added=time_added
            )
        )

        return _vertex_cache[id]

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a Component instance based on
        name :param name:.

        :param name: The name attribute of the component serverside.
        :type name: str
        """

        try:
            d = g.V().has('active', True).has('category', Component.category) \
                .has('name', name) \
                .project('id', 'type_id', 'rev_ids', 'time_added') \
                .by(__.id_()) \
                .by(__.both(RelationComponentType.category).id_()) \
                .by(__.both(RelationVersion.category).id_().fold()) \
                .by(__.values('time_added')).next()
        except StopIteration:
            raise ComponentNotAddedError

        id, type_id, rev_ids, time_added = \
            d['id'], d['type_id'], d['rev_ids'], d['time_added']

        return Component._attrs_to_component(
            name,
            id,
            type_id,
            rev_ids,
            time_added
        )

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a Component instance based on
        the ID :param id:

        :param id: The ID of the component serverside.
        :type id: int
        """
        if id not in _vertex_cache:

            d = g.V(id).project('name', 'type_id', 'rev_ids', 'time_added') \
                .by(__.values('name')) \
                .by(__.both(RelationComponentType.category).id_()) \
                .by(__.both(RelationVersion.category).id_().fold()) \
                .by(__.values('time_added')).next()

            name, type_id, rev_ids, time_added = \
                d['name'], d['type_id'], d['rev_ids'], d['time_added']

            return Component._attrs_to_component(
                name,
                id,
                type_id,
                rev_ids,
                time_added
            )

        else:
            return _vertex_cache[id]

    @classmethod
    def get_list(cls,
                 range: tuple,
                 order_by: str,
                 order_direction: str,
                 filters: list = []):
        """
        Return a list of Components based in the range :param range:,
        based on the filters in :param filters:, and order them based on 
        :param order_by: in the direction :param order_direction:.

        :param range: The range of Components to query
        :type range: tuple[int, int]

        :param order_by: What to order the components by. Must be in
        {'name', 'type', 'version'}
        :type order_by: str

        :param order_direction: Order the components by ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param filters: A list of 3-tuples of the format (name, ctype, version)
        :type order_by: list

        :return: A list of Component instances.
        :rtype: list[Component]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name', 'type', 'version'}

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        traversal = g.V().has('active', True).has('category', Component.category)

        # FILTERS

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 3

                contents = []

                # substring of component name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationComponentType.category).has(
                            'name',
                            f[1]
                        )
                    )

                    # component version

                    if f[2] != "":
                        contents.append(
                            __.both(RelationVersion.category).has(
                                'name',
                                f[2]
                            )
                        )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        # chr(0x10FFFF) is the "biggest" character in unicode

        if order_by == 'version':
            traversal = traversal.order() \
                .by(
                    __.coalesce(
                        __.both(RelationVersion.category).values('name'),
                        __.constant(chr(0x10FFFF))
                    ),
                    direction
            ) \
                .by('name', Order.asc) \
                .by(
                    __.both(RelationComponentType.category).values('name'),
                    Order.asc
            )

        elif order_by == 'type':
            traversal = traversal.order() \
                .by(
                    __.both(RelationComponentType.category).values('name'),
                    direction
            ) \
                .by('name', Order.asc) \
                .by(
                    __.coalesce(
                        __.both(RelationVersion.category).values('name'),
                        __.constant(chr(0x10FFFF))
                    ),
                    Order.asc
            )

        else:
            traversal = traversal.order() \
                .by('name', direction) \
                .by(
                    __.both(RelationComponentType.category).values('name'),
                    Order.asc
            ) \
                .by(
                    __.coalesce(
                        __.both(RelationVersion.category).values('name'),
                        __.constant(chr(0x10FFFF))
                    ),
                    Order.asc,
            )

        cs = traversal.range(range[0], range[1]) \
            .project('id', 'name', 'type_id', 'rev_ids', 'time_added') \
            .by(__.id_()) \
            .by(__.values('name')) \
            .by(__.both(RelationComponentType.category).id_()) \
            .by(__.both(RelationVersion.category).id_().fold()) \
            .by(__.values('time_added')) \
            .toList()

        components = []

        for d in cs:
            id, name, type_id, rev_ids, time_added = d['id'], d['name'], \
                d['type_id'], d['rev_ids'], d['time_added']

            components.append(
                Component._attrs_to_component(
                    id=id,
                    name=name,
                    type_id=type_id,
                    rev_ids=rev_ids,
                    time_added=time_added
                )
            )

        return components

    @classmethod
    def get_count(cls, filters: str):
        """Return the count of components given a list of filters.

        :param filters: A list of 3-tuples of the format (name, ctype, version)
        :type order_by: list

        :return: The number of Components.
        :rtype: int
        """

        traversal = g.V().has('active', True).has('category', Component.category)

        # FILTERS

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 3

                contents = []

                # substring of component name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationComponentType.category).has(
                            'name',
                            f[1]
                        )
                    )

                    # component version

                    if f[2] != "":
                        contents.append(
                            __.both(RelationVersion.category).has(
                                'name',
                                f[2]
                            )
                        )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        return traversal.count().next()

    def as_dict(self, time: int = None):
        """Return a dictionary representation of this Component at time
        :param time:.

        :param time: The time to check the component at. Pass `None` to get
        properties/flags/connexions at all times.
        :type time: int or None

        :return: A dictionary representation of this Components's attributes.
        :rtype: dict
        """

        prop_dicts = [{**prop.as_dict(), **rel.as_dict()} \
            for (prop, rel) in self.get_all_properties()
        ]

        conn_dicts = [{**{"name": comp.name}, **rel.as_dict()} \
            for (comp, rel) in self.get_all_connections()
        ]

        flag_dicts = [flag.as_dict() for flag in self.get_all_flags()]

        subcomponent_dicts = [{"name": subcomponents.name} \
            for subcomponents in self.get_all_subcomponents()
        ]
        
        supercomponent_dicts = [{"name": supercomponents.name} \
            for supercomponents in self.get_all_supercomponents()
        ]

        return {
            'name': self.name,
            'type': self.type.as_dict(),
            'version': self.version.as_dict() if self.version else {},
            'time_added': self.time_added,
            'properties': prop_dicts,
            'connections': conn_dicts,
            'flags': flag_dicts,
            'subcomponents': subcomponent_dicts,
            'supercomponents': supercomponent_dicts
        }


class PropertyType(Vertex):
    """
    The representation of a property type.

    :ivar name: The name of the property type.
    :ivar units: The units of the values of the properties 
    associated with the property type.
    :ivar allowed_regex: The regular expression for the allowed values of
    the properties associated with this property type.
    :ivar n_values: The expected number of values for the properties of this
    property type.
    :ivar comments: Additional comments about the property type.
    :ivar allowed_types: The allowed component types of the property type 
    Vertex, as a list of ComponentType attributes.
    """

    category: str = "property_type"

    name: str
    units: str
    allowed_regex: str
    n_values: int
    comments: str
    allowed_types: List[ComponentType]

    def __new__(
        cls, name: str, units: str, allowed_regex: str,
        n_values: int, allowed_types: List[ComponentType], comments: str = "",
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Return a PropertyType instance given the desired attributes.

        :param name: The name of the property type. 
        :type name: str

        :param units: The units which the values of the properties belonging
        to this type are to be in. 
        :type units: str

        :param allowed_regex: The regular expression that the values of the
        properties of this property type must adhere to. 
        :type allowed_regex: str

        :param n_values: The number of values that the properties of this
        property type must have. 
        :type n_values: int

        :param allowed_types: The component types that may have properties
        of this property type.
        :type allowed_types: List[ComponentType]

        :param comments: The comments attached to the property type, 
        defaults to ""
        :str comments: str  

        :param id: The serverside ID of the PropertyType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
        self, name: str, units: str, allowed_regex: str,
        n_values: int, allowed_types: List[ComponentType], comments: str = "",
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Initialize a PropertyType instance given the desired attributes.

        :param name: The name of the property type. 
        :type name: str

        :param units: The units which the values of the properties belonging
        to this type are to be in. 
        :type units: str

        :param allowed_regex: The regular expression that the values of the
        properties of this property type must adhere to. 
        :type allowed_regex: str

        :param n_values: The number of values that the properties of this
        property type must have. 
        :type n_values: int

        :param allowed_types: The component types that may have properties
        of this property type.
        :type allowed_types: List[ComponentType]

        :param comments: The comments attached to the property type, 
        defaults to ""
        :str comments: str  

        :param id: The serverside ID of the PropertyType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        self.name = name
        self.units = units
        self.allowed_regex = allowed_regex
        self.n_values = n_values
        self.comments = comments
        self.allowed_types = allowed_types

        if len(self.allowed_types) == 0:
            raise PropertyTypeZeroAllowedTypesError(
                f"No allowed types were specified for property type {name}."
            )

        Vertex.__init__(self, id=id)

    def as_dict(self):
        """Return dictionary representation."""
        return {
            'name': self.name,
            'units': self.units,
            'comments': self.comments
        }

    def add(self):
        """Add this PropertyType to the serverside.
        """

        # If already added, raise an error!
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"PropertyType with name {self.name} " +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'units': self.units,
            'allowed_regex': self.allowed_regex,
            'n_values': self.n_values,
            'comments': self.comments
        }

        Vertex.add(self, attributes)

        for ctype in self.allowed_types:

            if not ctype.added_to_db():
                ctype.add()

            e = RelationPropertyAllowedType(
                inVertex=ctype,
                outVertex=self
            )

            e.add()

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the PropertyType vertex in the serverside.

        :param newVertex: The new PropertyType vertex that is replacing the old PropertyType vertex.
        :type newVertex: PropertyType

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """Return whether this PropertyType is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform a 
        query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', PropertyType.category)
                .has('name', self.name).has('active', True).count().next() > 0
            )
        )

    @classmethod
    def _attrs_to_type(
        cls,
        name: str, units: str, allowed_regex: str,
        n_values: int, allowed_types: List[ComponentType], comments: str = "",
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """Given the id and attributes of a PropertyType, see if one
        exists in the cache. If so, return the cached PropertyType.
        Otherwise, create a new one, cache it, and return it.

        :param name: The name of the property type. 
        :type name: str

        :param units: The units which the values of the properties belonging
        to this type are to be in. 
        :type units: str

        :param allowed_regex: The regular expression that the values of the
        properties of this property type must adhere to. 
        :type allowed_regex: str

        :param n_values: The number of values that the properties of this
        property type must have. 
        :type n_values: int

        :param allowed_types: The component types that may have properties
        of this property type.
        :type allowed_types: List[ComponentType]

        :param comments: The comments attached to the property type, 
        defaults to ""
        :type comments: str  

        :param id: The serverside ID of the PropertyType, 
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                PropertyType(
                    name=name,
                    units=units,
                    allowed_regex=allowed_regex,
                    n_values=n_values,
                    allowed_types=allowed_types,
                    comments=comments,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a PropertyType instance based on
        name :param name:.

        :param name: The name attribute of the property type
        :type name: str
        """

        try:
            d = g.V().has('active', True) \
                .has('category', PropertyType.category).has('name', name) \
                .project('id', 'attrs', 'type_ids') \
                .by(__.id_()) \
                .by(__.valueMap()) \
                .by(__.both(RelationPropertyAllowedType.category) \
                .id_().fold()) \
                .next()
        except StopIteration:
            raise PropertyTypeNotAddedError

        # to access attributes from attrs, do attrs[...][0]
        id, attrs, ctype_ids = d['id'], d['attrs'], d['type_ids']

        if id not in _vertex_cache:

            ctypes = []

            for ctype_id in ctype_ids:
                ctypes.append(ComponentType.from_id(ctype_id))

            Vertex._cache_vertex(
                PropertyType(
                    name=name,
                    units=attrs['units'][0],
                    allowed_regex=attrs['allowed_regex'][0],
                    n_values=attrs['n_values'][0],
                    comments=attrs['comments'][0],
                    allowed_types=ctypes,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a PropertyType instance based on
        the ID.

        :param id: The serverside ID of the PropertyType vertex.
        :type id: int
        :return: Return a PropertyType from that ID.
        :rtype: PropertyType
        """

        if id not in _vertex_cache:

            d = g.V(id).project('attrs', 'type_ids') \
                .by(__.valueMap()) \
                .by(__.both(RelationPropertyAllowedType.category).id_().fold()) \
                .next()

            # to access attributes from attrs, do attrs[...][0]
            attrs, ctype_ids = d['attrs'], d['type_ids']

            ctypes = []

            for ctype_id in ctype_ids:
                ctypes.append(ComponentType.from_id(ctype_id))

            Vertex._cache_vertex(
                PropertyType(
                    name=attrs['name'][0],
                    units=attrs['units'][0],
                    allowed_regex=attrs['allowed_regex'][0],
                    n_values=attrs['n_values'][0],
                    comments=attrs['comments'][0],
                    allowed_types=ctypes,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_list(cls,
                 range: tuple,
                 order_by: str,
                 order_direction: str,
                 filters: list = []):
        """
        Return a list of PropertyTypes in the range :param range:,
        based on the filters in :param filters:,
        and order them based on  :param order_by: in the direction 
        :param order_direction:.

        :param range: The range of PropertyTypes to query
        :type range: tuple[int, int]

        :param order_by: What to order the PropertyTypes by. Must be in
        {'name', 'allowed_type'}
        :type order_by: str

        :param order_direction: Order the PropertyTypes by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param filters: A list of 2-tuples of the format (name, ctype)
        :type order_by: list

        :return: A list of PropertyType instances.
        :rtype: list[PropertyType]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name', 'allowed_type'}

        traversal = g.V().has('active', True).has('category', PropertyType.category)

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 2

                contents = []

                # substring of property type name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationPropertyAllowedType.category).has(
                            'name',
                            f[1]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        # How to order the property types.
        if order_by == 'name':
            traversal = traversal.order().by('name', direction) \
                .by(
                    __.both(
                        RelationPropertyAllowedType.category
                    ).values('name'),
                    Order.asc
            )
        elif order_by == 'allowed_type':
            traversal = traversal.order().by(
                __.both(
                    RelationPropertyAllowedType.category
                ).values('name'),
                direction
            ).by('name', Order.asc)

        # Component type query to DB
        pts = traversal.range(range[0], range[1]) \
            .project('id', 'attrs', 'type_ids') \
            .by(__.id_()) \
            .by(__.valueMap()) \
            .by(__.both(RelationPropertyAllowedType.category).id_().fold()) \
            .toList()

        types = []

        for entry in pts:
            id, ctype_ids, attrs = entry['id'], entry['type_ids'], \
                entry['attrs']

            ctypes = []

            for ctype_id in ctype_ids:
                ctypes.append(ComponentType.from_id(ctype_id))

            types.append(
                PropertyType._attrs_to_type(
                    id=id,
                    name=attrs['name'][0],
                    units=attrs['units'][0],
                    allowed_regex=attrs['allowed_regex'][0],
                    n_values=attrs['n_values'][0],
                    comments=attrs['comments'][0],
                    allowed_types=ctypes,
                )
            )

        return types

    @classmethod
    def get_count(cls, filters: list):
        """Return the count of PropertyType given a list of filters

        :param filters: A list of 2-tuples of the format (name, ctype)
        :type order_by: list

        :return: The number of PropertyType that agree with
        :param filters:.
        :rtype: int
        """

        traversal = g.V().has('active', True).has('category', PropertyType.category)

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 2

                contents = []

                # substring of property type name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # component type
                if f[1] != "":
                    contents.append(
                        __.both(RelationPropertyAllowedType.category).has(
                            'name',
                            f[1]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        return traversal.count().next()

        # traversal = g.V().has('category', PropertyType.category) \
        #     .has('name', TextP.containing(name_substring))

        # # https://groups.google.com/g/gremlin-users/c/FKbxWKG-YxA/m/kO1hc0BDCwAJ
        # if order_by == "name":
        #     traversal = traversal.order().by(
        #         __.coalesce(__.values('name'), constant("")),
        #         direction
        #     )

        # ids = traversal.range(range[0], range[1]).id().toList()

        # property_types = []

        # for id in ids:

        #     property_types.append(
        #         PropertyType.from_id(id)
        #     )

        # return property_types


class Property(Vertex):
    """The representation of a property.

    :ivar values: The values contained within the property.
    :ivar type: The PropertyType instance representing the property
    type of this property.
    """

    category: str = "property"

    values: List[str]
    type: PropertyType

    def __init__(
        self, values: List[str], type: PropertyType,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        # If the user passes a string rather than a list of strings, fix it.
        if isinstance(values, str):
            values = [values]

        if len(values) != type.n_values:
            raise PropertyWrongNValuesError

        for val in values:

            # If the value does not match the property type's regex
            if not bool(re.fullmatch(type.allowed_regex, val)):
                raise PropertyNotMatchRegexError(
                    f"Property with values {values} of type " +
                    f"{type.name} does not match regex " +
                    f"{type.allowed_regex} for value {val}."
                )

        self.values = values
        self.type = type

        Vertex.__init__(self, id=id)

    def _add(self):
        """
        Add this Property to the serverside.
        """

        attributes = {
            'values': self.values
        }

        Vertex.add(self, attributes)

        if not self.type.added_to_db():
            self.type.add()

        e = RelationPropertyType(
            inVertex=self.type,
            outVertex=self
        )

        e.add()

    def as_dict(self):
        """Return a dictionary representation of this property."""
        return {
            'values': self.values,
            'type': self.type.as_dict()
        }

    @classmethod
    def from_id(cls, id: int):
        """Given an ID of a serverside property vertex, 
        return a Property instance. 
        """

        if id not in _vertex_cache:

            d = g.V(id).project('values', 'ptype_id') \
                .by(__.properties('values').value().fold()) \
                .by(__.both(RelationPropertyType.category).id_()).next()

            values, ptype_id = d['values'], d['ptype_id']

            if not isinstance(values, list):
                values = [values]

            Vertex._cache_vertex(
                Property(
                    values=values,
                    type=PropertyType.from_id(ptype_id),
                    id=id
                )
            )

        return _vertex_cache[id]


class FlagType(Vertex):
    """The representation of a flag type. 

    :ivar name: The name of the flag type.
    :ivar comments: Comments about the flag type.
    """

    category: str = "flag_type"

    name: str
    comments: str

    def __new__(
        cls, name: str, comments: str = "", id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Return a FlagType instance given the desired attributes.

        :param name: The name of the flag type
        :type name: str

        :param comments: The comments attached to this flag type, defaults to ""
        :type comments: str

        :param id: The serverside ID of the FlagType,
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
        self, name: str, comments: str = "", id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """Initialize a FlagType instance given the desired attributes.

        :param name: The name of the flag type
        :type name: str

        :param comments: The comments attached to this flag type, defaults to ""
        :type comments: str

        :param id: The serverside ID of the FlagType,
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        self.name = name
        self.comments = comments

        Vertex.__init__(self, id=id)

    def as_dict(self):
        """Return a dictionary representation."""
        return {
            "name": self.name,
            "comments": self.comments
        }

    def add(self):
        """Add this FlagType to the database.
        """

        # If already added.
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"FlagType with name {self.name} " +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments
        }

        Vertex.add(self=self, attributes=attributes)

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the FlagType vertex in the serverside.

        :param newVertex: The new FlagType vertex that is replacing the old FlagType vertex.
        :type newVertex: FlagType

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """Return whether this FlagType is added to the database,
        that is, whether the ID is not the virtual ID placeholder and perform a 
        query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', FlagType.category)
                .has('name', self.name).has('active', True).count().next() == 1
            )
        )

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a FlagType instance based on
        flag type of name :param name:.

        :param name: The name of the flag type.
        :type name: str

        :return: A FlagType instance with the correct name, comments, and 
        ID.
        :rtype: FlagType
        """

        try:
            d = g.V().has('active', True).has('category', FlagType.category) \
                .has('name', name).as_('v').valueMap().as_('props') \
                .select('v').id_().as_('id').select('props', 'id').next()
        except StopIteration:
            raise FlagTypeNotAddedError

        props, id = d['props'], d['id']

        Vertex._cache_vertex(
            FlagType(
                name=name,
                comments=props['comments'][0],
                id=id
            )
        )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a FlagType instance based on
        the ID.

        :param id: The serverside ID of the FlagType vertex.
        :type id: int

        :return: Return a FlagType from that ID.
        :rtype: FlagType
        """

        if id not in _vertex_cache:

            d = g.V(id).valueMap().next()

            Vertex._cache_vertex(
                FlagType(
                    name=d['name'][0],
                    comments=d['comments'][0],
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def _attrs_to_type(cls, name: str, comments: str, id: int):
        """Given name, comments and id of a FlagType, see if one
        exists in the cache. If so, return the cached FlagType.
        Otherwise, create a new one, cache it, and return it.

        :param name: The name of the FlagType vertex
        :type name: str
        :param comments: Comments associated with the FlagType vertex
        :type comments: str
        :param id: The ID of the FlagType vertex.
        :type id: int
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                FlagType(
                    name=name,
                    comments=comments,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_list(
        cls,
        range: tuple,
        order_by: str,
        order_direction: str,
        name_substring: str
    ):
        """
        Return a list of FlagTypes based in the range :param range:,
        based on the name substring in :param name_substring:, 
        and order them based on :param order_by: 
        in the direction :param order_direction:.

        :param range: The range of FlagTypes to query. If the second
        coordinate is -1, then the range is (range[1], inf)
        :type range: tuple[int, int]

        :param order_by: What to order the flag types by. Must be in
        {'name'}
        :type order_by: str

        :param order_direction: Order the flag types by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param name_substring: What substring of the name property of the
        flag type to filter by.
        :type name_substring: str

        :return: A list of FlagType instances.
        :rtype: list[FlagType]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name'}

        traversal = g.V().has('active', True).has('category', FlagType.category) \
            .has('name', TextP.containing(name_substring))

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        # How to order the flag types.
        # This coalesce thing is done to prevent "property does not exist" error
        # not sure why it happens as the 'name' property will ALWAYS exist...
        # but maybe the traversal somehow catches other vertices not of this
        # type...
        if order_by == 'name':
            traversal = traversal.order().by(
                __.coalesce(__.values('name'), constant("")),
                direction
            )

        # Component type query to DB
        cts = traversal.range(range[0], range[1]) \
            .project('id', 'name', 'comments') \
            .by(__.id_()) \
            .by(__.values('name')) \
            .by(__.values('comments')) \
            .toList()

        flag_types = []

        for entry in cts:
            id, name, comments = entry['id'], entry['name'], entry['comments']

            flag_types.append(
                FlagType._attrs_to_type(
                    id=id,
                    name=name,
                    comments=comments
                )
            )

        return flag_types

    @classmethod
    def get_count(cls, name_substring: str):
        """Return the count of FlagTypes given a substring of the name
        property.

        :param name_substring: A substring of the name property of the
        FlagType
        :type name_substring: str

        :return: The number of FlagTypes that contain 
        :param name_substring: as a substring in the name property.
        :rtype: int
        """

        return g.V().has('active', True).has('category', FlagType.category) \
            .has('name', TextP.containing(name_substring)) \
            .count().next()


class FlagSeverity(Vertex):
    """
    The representation of a flag severity.

    :ivar name: The name of the severity.
    """
    category: str = "flag_severity"

    name: str

    def __new__(cls, name: str, id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Return a FlagSeverity instance given the desired attribute.

        :param name: Indicates the severity of a flag.
        :type name: str

        :param id: The serverside ID of the FlagType,
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(self, name: str, id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Initialize a FlagSeverity instance given the FlagSeverity instance given the desired attributes.

        :param name: Indicates the severity of a flag.
        :type name: str

        :param id: The serverside ID of the FlagType,
        defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        self.name = name

        Vertex.__init__(self, id=id)

    def as_dict(self):
        """Return a dictionary representation."""
        return {"name": self.name}

    def add(self):
        """Add this FlagSeverity to the database."""

        # If already added.
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"FlagSeverity with name {self.name}" +
                "already exists in the database."
            )

        attributes = {
            'name': self.name
        }

        Vertex.add(self=self, attributes=attributes)

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the FlagSeverity vertex in the serverside.

        :param newVertex: The new FlagSeverity vertex that is replacing the old FlagSeverity vertex.
        :type newVertex: FlagSeverity

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """
        Return whether this FlagSeverity is added to the database, that is, whether the ID is not the virtual ID placeholder and perform a query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', FlagSeverity.category).has(
                    'name', self.name).has('active', True).count().next() == 1
            )
        )

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a FlagSeverity instance based on Flag Severity name :param name:.

        :param name: Indicated the severity of a flag.
        :type name: str

        :return: A FlagSeverity instance with the correct name and ID.
        :rtype: FlagSeverity.
        """

        try:
            d = g.V().has('active', True) \
                .has('category', FlagSeverity.category).has('name', name) \
                .as_('v').valueMap().as_('props').select('v').id_().as_('id') \
                .select('props', 'id').next()
        except StopIteration:
            raise FlagSeverityNotAddedError

        props, id = d['props'], d['id']

        Vertex._cache_vertex(
            FlagSeverity(
                name=name,
                id=id
            )
        )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a FlagSeverity instance based on the ID.

        :param id: The serverside ID of the FlagSeverity vertex.
        :type id: int

        :return: Return a FlagSeverity from that ID.
        :rtype: FlagSeverity
        """

        if id not in _vertex_cache:

            d = g.V(id).valueMap().next()

            Vertex._cache_vertex(
                FlagSeverity(
                    name=d['name'][0],
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def _attrs_to_type(cls, name: str, id: int):
        """Given name of a FlagSeverity, see if one
        exists in the cache. If so, return the cached FlagSeverity.
        Otherwise, create a new one, cache it, and return it.

        :param name: Indicates the severity of flag.
        :type name: str

        :param id: The ID of the ComponentType vertex.
        :type id: int
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                FlagSeverity(
                    name=name,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_list(
        cls,
        range: tuple,
        order_by: str,
        order_direction: str
    ):
        """
        Return a list of FlagSeverity based in the range :param range:, 
        and order them based on :param order_by: 
        in the direction :param order_direction:.

        :param range: The range of FlagSeverity to query. If the second
        coordinate is -1, then the range is (range[1], inf)
        :type range: tuple[int, int]

        :param order_by: What to order the flag severities by. Must be in
        {'name'}
        :type order_by: str

        :param order_direction: Order the flag severities by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :return: A list of FlagSeverity instances.
        :rtype: list[FlagSeverity]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name'}

        traversal = g.V().has('active', True).has('category', FlagSeverity.category) \


        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        # How to order the flag severities.
        # This coalesce thing is done to prevent "property does not exist" error
        # not sure why it happens as the 'name' property will ALWAYS exist...
        # but maybe the traversal somehow catches other vertices not of this
        # type...
        if order_by == 'name':
            traversal = traversal.order().by('name', direction
                                             )

        # flag severity query to DB
        fs = traversal.range(range[0], range[1]) \
            .project('id', 'name') \
            .by(__.id_()) \
            .by(__.values('name')) \
            .toList()

        flag_severities = []

        for entry in fs:
            id, name = entry['id'], entry['name']

            flag_severities.append(
                FlagSeverity._attrs_to_type(
                    id=id,
                    name=name,

                )
            )

        return flag_severities


class Flag(Vertex):
    """
    The representation of a flag component.

    :ivar name: The name of the flag.
    :ivar comments: Comments associated with the flag in general.
    :ivar start: The starting timestamp of the flag.
    :ivar end: The ending timestamp of the flag.
    :ivar severity: The FlagSeverity instance representing the severity of the
        flag.
    :ivar type: The FlagType instance representing the type of the flag.
    :ivar components: A list of Component instances related to the flag.
    """

    category: str = "flag"

    name: str
    comments: str
    start: Timestamp
    end: Timestamp
    severity: FlagSeverity
    type: FlagType
    components: List[Component]

    def __new__(cls, name: str, start: Timestamp, severity: FlagSeverity, 
                type: FlagType, comments: str = "", end: Timestamp = None, 
                components: List[Component] = [],
                id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Return a Flag instance with the specified properties.

        :param name: The name of the flag.
        :type name: str
        :param comments: Comments associated with the flag in general,
            defaults to ""
        :type comments: str, optional
        :param start: The starting timestamp of the flag.
        :type start: Timestamp
        :param severity: The flag severity that indicates the severity of the
            flag.
        :type severity: FlagSeverity
        :param type: The flag type that indicates the type of the flag.
        :type type: FlagType
        :param components: A list of The flag components that have this flag.
        :type components: List[Component]
        :param end: The ending timestamp of the flag.
        :type end: Timestamp or None.
        """
        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(cls, name: str, start: Timestamp, severity: FlagSeverity, 
                type: FlagType, comments: str = "", end: Timestamp = None, 
                components: List[Component] = [],
                id: int = VIRTUAL_ID_PLACEHOLDER):
        self.name = name
        self.comments = comments
        self.start = start
        self.severity = severity
        self.type = type
        self.components = components
        if end:
            self.end = end
        else:
            self.end = Timestamp(EXISTING_RELATION_END_PLACEHOLDER, "",
                                 EXISTING_RELATION_END_EDIT_PLACEHOLDER, "")

        Vertex.__init__(self=self, id=id)

    def as_dict(self):
        """Return a dictionary representation."""
        return {
            "name": self.name,
            "comments": self.comments,
            "type": self.type.as_dict(),
            "severity": self.severity.as_dict(),
            "start": {
                "time": self.start.time,
                "uid": self.start.uid,
                "edit_time": self.start.edit_time,
                "comments": self.start.comments
            },
            "end": {
                "time": self.end.time,
                "uid": self.end.uid,
                "edit_time": self.end.edit_time,
                "comments": self.end.comments
            }
        }


    def add(self):
        """
        Add this Flag instance to the database.
        """

        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"Flag with name {self.name}" +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments,
            'start_time': self.start.time,
            'start_uid': self.start.uid,
            'start_edit_time': self.start.edit_time,
            'start_comments': self.start.comments,
            'end_time': self.end.time,
            'end_uid': self.end.uid,
            'end_edit_time': self.end.edit_time,
            'end_comments': self.end.comments
        }

        Vertex.add(self=self, attributes=attributes)

        if not self.type.added_to_db():
            self.type.add()

        e = RelationFlagType(
            inVertex=self.type,
            outVertex=self
        )

        e.add()

        if not self.severity.added_to_db():
            self.severity.add()

        e = RelationFlagSeverity(
            inVertex=self.severity,
            outVertex=self
        )

        e.add()

        for c in self.components:

            if not c.added_to_db():
                c.add()

            e = RelationFlagComponent(
                inVertex=c,
                outVertex=self
            )

            e.add()

    def replace(self, newVertex, disable_time: int = int(time.time())):
        """Replaces the Flag vertex in the serverside.

        :param newVertex: The new Flag vertex that is replacing the old Flag vertex.
        :type newVertex: Flag

        :param disable_time: When this vertex was disabled in the database (UNIX time).
        :type disable_time: int
        """

        # Step 1
        g.V(self.id()).property(
            'active', False).property('time_disabled', disable_time).iterate()

        # Step 2
        newVertex.add()

        # Step 3
        newVertexId = newVertex.id()

        Vertex.replace(self=self, id=newVertexId)

    def added_to_db(self) -> bool:
        """Return whether this Flag is added to the database,that is, whether the ID is not the virtual ID placeholder and perform a query to the database if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', Flag.category).has(
                    'name', self.name).has('active', True).count().next() > 0
            )
        )

    @classmethod
    def __attrs_to_flag__(cls, name: str, start: Timestamp,
                          severity: FlagSeverity, type: FlagType,
                          comments: str = "", end: Timestamp = None, 
                          components: List[Component] = [],
                          id: int = VIRTUAL_ID_PLACEHOLDER):
        """Given the id and attributes of a Flag, see if one exists in the
        cache. If so, return the cached Flag. Otherwise, create a new one,
        cache it, and return it.

        :param name: The name of the flag.
        :type name: str
        :param comments: Comments associated with the flag in general,
            defaults to ""
        :type comments: str, optional
        :param start: The starting timestamp of the flag.
        :type start: Timestamp
        :param severity: The flag severity that indicates the severity of the
            flag.
        :type severity: FlagSeverity
        :param type: The flag type that indicates the type of the flag.
        :type type: FlagType
        :param components: A list of The flag components that have this flag.
        :type components: List[Component]
        :param end: The ending timestamp of the flag.
        :type end: Timestamp or None.
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                Flag(
                    name=name,
                    comments=comments,
                    start=start,
                    severity=severity,
                    type=type,
                    components=components,
                    end=end,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a Flag instance based on the name
        :param name:, connected to the necessary Components, FlagType
        instances and FlagSeverity instance.

        :param name: The name of the Flag instance
        :type name: str
        """

        try:
            d = g.V().has('active', True).has('category', Flag.category) \
                .has('name', name) \
                .project('id', 'attrs', 'type_id', 'severity_id',
                         'component_ids') \
                .by(__.id_()) \
                .by(__.valueMap()) \
                .by(__.both(RelationFlagType.category).id_()) \
                .by(__.both(RelationFlagSeverity.category).id_()) \
                .by(__.both(RelationFlagComponent.category).id_().fold()).next()
        except StopIteration:
            raise FlagNotAddedError

        id, attrs, type_id, severity_id, component_ids = d['id'], d['attrs'], \
            d['type_id'], d['severity_id'], d['component_ids']

        if id not in _vertex_cache:

            Vertex._cache_vertex(FlagType.from_id(type_id))

            Vertex._cache_vertex(FlagSeverity.from_id(severity_id))

            components = []

            for c_id in component_ids:
                components.append(Component.from_id(c_id))

            Vertex._cache_vertex(
                Flag(
                    name=name,
                    comments=attrs['comments'][0],
                    start=Timestamp(
                        attrs['start_time'][0],
                        attrs['start_uid'][0],
                        attrs['start_edit_time'][0],
                        attrs['start_comments'][0]
                    ),
                    severity=_vertex_cache[severity_id],
                    type=_vertex_cache[type_id],
                    components=components,
                    end=Timestamp(
                        attrs['end_time'][0],
                        attrs['end_uid'][0],
                        attrs['end_edit_time'][0],
                        attrs['end_comments'][0]
                    ),
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """Given an ID of a serverside flag vertex, return a Flag instance.
        """

        if id not in _vertex_cache:

            d = g.V(id).project('attrs', 'fseverity_id', 'ftype_id', 'fcomponent_ids').by(__.valueMap()).by(__.both(RelationFlagSeverity.category).id_()).by(
                __.both(RelationFlagType.category).id_()).by(__.both(RelationFlagComponent.category).id_().fold()).next()

            # to access attributes from attrs, do attrs[...][0]
            attrs, fseverity_id, ftype_id, fcomponent_ids = d['attrs'], d[
                'fseverity_id'], d['ftype_id'], d['fcomponent_ids']

            components = []

            for component_id in fcomponent_ids:
                components.append(Component.from_id(component_id))

            Vertex._cache_vertex(
                Flag(
                    name=attrs['name'][0],
                    comments=attrs['comments'][0],
                    start=Timestamp(
                        attrs['start_time'][0],
                        attrs['start_uid'][0],
                        attrs['start_edit_time'][0],
                        attrs['start_comments'][0]
                    ),
                    severity=FlagSeverity.from_id(fseverity_id),
                    type=FlagType.from_id(ftype_id),
                    components=components,
                    end=Timestamp(
                        attrs['end_time'][0],
                        attrs['end_uid'][0],
                        attrs['end_edit_time'][0],
                        attrs['end_comments'][0]
                    ),
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def get_list(cls,
                 range: tuple,
                 order_by: str,
                 order_direction: str,
                 filters: list = []):
        """
        Return a list of Flags in the range :param range:,
        based on the filters in :param filters:,
        and order them based on  :param order_by: in the direction 
        :param order_direction:.

        :param range: The range of Flag to query
        :type range: tuple[int, int]

        :param order_by: What to order the Flag by. Must be in
        {'name', 'type','severity'}
        :type order_by: str

        :param order_direction: Order the Flag by 
        ascending or descending?
        Must be in {'asc', 'desc'}
        :type order_by: str

        :param filters: A list of 3-tuples of the format (name, ftype,fseverity)
        :type order_by: list

        :return: A list of Flag instances.
        :rtype: list[Flag]
        """

        assert order_direction in {'asc', 'desc'}

        assert order_by in {'name', 'type', 'severity'}

        traversal = g.V().has('active', True).has('category', Flag.category)

        # if order_direction is not asc or desc, it will just sort by asc.
        # Keep like this if removing the assert above only in production.
        if order_direction == 'desc':
            direction = Order.desc
        else:
            direction = Order.asc

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 3

                contents = []

                # substring of flag name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # flag type
                if f[1] != "":
                    contents.append(
                        __.both(RelationFlagType.category).has(
                            'name',
                            f[1]
                        )
                    )

                # flag severity
                if f[2] != "":
                    contents.append(
                        __.both(RelationFlagSeverity.category).has(
                            'name',
                            f[2]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        # How to order the flags.
        if order_by == 'name':
            traversal = traversal.order().by('name', direction) \
                .by(
                    __.both(
                        RelationFlagType.category
                    ).values('name'),
                    Order.asc
            ).by(
                __.both(RelationFlagSeverity.category).values(
                    'name'), Order.asc
            )

        elif order_by == 'type':
            traversal = traversal.order().by(
                __.both(
                    RelationFlagType.category
                ).values('name'),
                direction
            ).by('name', Order.asc).by(
                __.both(
                    RelationFlagSeverity.category
                ).values('name'), Order.asc
            )

        elif order_by == 'severity':
            traversal = traversal.order().by(
                __.both(
                    RelationFlagSeverity.category
                ).values('name'),
                direction
            ).by('name', Order.asc).by(
                __.both(RelationFlagType.category).values('name'), Order.asc
            )

        # flag query to DB
        fs = traversal.range(range[0], range[1]) \
            .project('id', 'attrs', 'ftype_id', 'fseverity_id', 'fcomponent_ids') \
            .by(__.id_()) \
            .by(__.valueMap()) \
            .by(__.both(RelationFlagType.category).id_()).by(__.both(RelationFlagSeverity.category).id_()).by(__.both(RelationFlagComponent.category).id_().fold()) \
            .toList()

        flags = []

        for entry in fs:
            id, ftype_id, fseverity_id, fcomponent_ids, attrs = entry['id'], entry['ftype_id'], entry['fseverity_id'], entry['fcomponent_ids'], \
                entry['attrs']

            fcomponents = []

            for fcomponent_id in fcomponent_ids:
                fcomponents.append(Component.from_id(fcomponent_id))

            flags.append(
                Flag._attrs_to_flag(
                    id=id,
                    name=attrs['name'][0],
                    comments=attrs['comments'][0],
                    start=Timestamp(
                        attrs['start_time'][0],
                        attrs['start_uid'][0],
                        attrs['start_edit_time'][0],
                        attrs['start_comments'][0]
                    ),
                    severity=FlagSeverity.from_id(fseverity_id),
                    type=FlagType.from_id(ftype_id),
                    components=fcomponents,
                    end=Timestamp(
                        attrs['end_time'][0],
                        attrs['end_uid'][0],
                        attrs['end_edit_time'][0],
                        attrs['end_comments'][0]
                    )
                )
            )

        return flags

    @classmethod
    def get_count(cls, filters: str):
        """Return the count of flags given a list of filters.

        :param filters: A list of 3-tuples of the format (name,ftype,fseverity)
        :type order_by: list

        :return: The number of flags.
        :rtype: int
        """
        traversal = g.V().has('active', True).has('category', Flag.category)

        # FILTERS

        if filters is not None:

            ands = []

            for f in filters:

                assert len(f) == 3

                contents = []

                # substring of flag name
                if f[0] != "":
                    contents.append(__.has('name', TextP.containing(f[0])))

                # flag type
                if f[1] != "":
                    contents.append(
                        __.both(RelationFlagType.category).has(
                            'name',
                            f[1]
                        )
                    )

                # flag severity
                if f[2] != "":
                    contents.append(
                        __.both(RelationFlagSeverity.category).has(
                            'name',
                            f[2]
                        )
                    )

                if len(contents) > 0:
                    ands.append(__.and_(*contents))

            if len(ands) > 0:
                traversal = traversal.or_(*ands)

        return traversal.count().next()

    def end_flag(
            self, end_time: int, end_uid: str, end_edit_time: int = int(time.time()), end_comments=""):
        """
        Given a flag, set the "end" attributes of the flag to indicate that this flag has been ended.

        :param time: The time at which the flag was ended (real time). This value has to be provided.
        :type time: int

        :param uid: The user that ended the flag.
        :type uid: str

        :param edit_time: The time at which the user made the change, defaults to int(time.time())
        :type edit_time: int, optional

        :param comments: Comments associated with ending the flag.
        :type comments: str, optional
        """

        if not self.added_to_db():
            raise FlagNotAddedError(
                f"Flag {self.name} has not yet been added to the database."
            )

        self.end_time = end_time
        self.end_uid = end_uid
        self.end_edit_time = end_edit_time
        self.end_comments = end_comments

        g.V(self.id()).property('end_time', end_time).property('end_uid', end_uid).property(
            'end_edit_time', end_edit_time).property('end_comments', end_comments).iterate()


class Permission(Vertex):
    """ The representation of a permission.

    :ivar name: The name of the permission.
    :ivar comments: Comments about the permission.
    """

    category: str = 'permission'

    name: str
    comments: str

    def __new__(
            cls, name: str, comments: str = '', id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Return a Permission instance given the desired attributes.

        :param name: The name of the permission.
        :type name: str

        :param comments: The comments attached to this permission, defaults to ""
        :type comments: str

        :param id: The serverside ID of the permission, defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(self, name: str, comments: str = " ", id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Initialize a Permission instance given the desired attributes.

        :param name: The name of the permission.
        :type name: str

        :param comments: The comments attached to this permission, defaults to ""
        :type comments: str

        :param id: The serverside ID of the permission, defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int, optional
        """

        self.name = name
        self.comments = comments

        Vertex.__init__(self, id=id)

    def add(self):
        """Add this permission to the database."""

        # if already added, raise an error!
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"Permission with name {self.name}" +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments
        }

        Vertex.add(self=self, attributes=attributes)

    def added_to_db(self) -> bool:
        """
        Return whether this Permission is added to the database, that is, whether the ID is not the Virtual ID placeholder and perform a query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', Permission.category).has(
                    'name', self.name).count().next() == 1
            )
        )

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a Permission instance based on permission :param name.

        :param name: The name of the permission.
        :type name: str

        :return: A Permission instance with the correct name, comments, and ID.
        :rtype: Permission
        """

        try:
            d = g.V().has('category', Permission.category).has('name', name) \
                .as_('v').valueMap().as_('props').select('v').id_().as_('id') \
                .select('props', 'id').next()
        except StopIteration:
            raise PermissionNotAddedError

        props, id = d['props'], d['id']

        Vertex._cache_vertex(
            Permission(
                name=name,
                comments=props['comments'][0],
                id=id
            )
        )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """ Query the database and return a Permission instance based on the ID.

        :param id: The serverside ID of the Permission vertex.
        :type id: int

        :return: Return a Perimssion from that ID.
        :rtype: Permission
        """

        if id not in _vertex_cache:
            d = g.V(id).valueMap().next()

            Vertex._cache_vertex(
                Permission(
                    name=d['name'][0],
                    comments=d['comments'][0],
                    id=id
                )
            )

        return _vertex_cache[id]


class UserGroup(Vertex):
    """ The representation of a user group.

    :ivar name: The name of the user group.
    :ivar comments: The comments assocaited with the group.
    :ivar permission: A list of Perimssion instances associated with this group.
    """

    category: str = 'user_group'

    name: str
    comments: str
    permission: List[Permission]

    def __init__(self, name: str, comments: str, permission: List[Permission], id: int = VIRTUAL_ID_PLACEHOLDER):

        self.name = name
        self.comments = comments
        self.permission = permission

        if len(self.permission) == 0:
            raise UserGroupZeroPermissionError(
                f"No permission were specified for user group {name}"
            )

        Vertex.__init__(self=self, id=id)

    def add(self):
        """
        Add this UserGroup instance to the database.
        """

        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"UserGroup with name {self.name}" +
                "already exists in the database."
            )

        attributes = {
            'name': self.name,
            'comments': self.comments
        }

        Vertex.add(self=self, attributes=attributes)

        for p in self.permission:

            if not p.added_to_db():
                p.add()

            e = RelationGroupAllowedPermission(
                inVertex=p,
                outVertex=self
            )

            e.add()

    def added_to_db(self) -> bool:
        """Return whether this UserGroup is added to the database, that is, whether the ID is not the virtual ID placeholder and perform a query to the database to determine if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        :rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', UserGroup.category).has(
                    'name', self.name).count().next() == 1
            )
        )

    @classmethod
    def from_db(cls, name: str):
        """Query the database and return a UserGroup instance based on the name :param name:, connected to the necessary Permission instances.

        :param name: The name of the UserGroup instance.
        :type name: str
        """

        try:
            d = g.V().has('category', UserGroup.category).has('name', name) \
                .project('id', 'attrs', 'permission_ids').by(__.id_()) \
                .by(__.valueMap()) \
                .by(__.both(RelationGroupAllowedPermission.category).id_() \
                .fold()).next()
        except StopIteration:
            raise UserGroupNotAddedError

        id, attrs, perimssion_ids = d['id'], d['attrs'], d['permission_ids']

        if id not in _vertex_cache:

            permissions = []

            for p_id in perimssion_ids:
                permissions.append(Permission.from_id(p_id))

            Vertex._cache_vertex(
                UserGroup(
                    name=name,
                    comments=attrs['comments'][0],
                    permission=permissions,
                    id=id
                )
            )

        return _vertex_cache[id]


class User(Vertex):
    """ The representation of a user.

    :ivar uname: Name used by the user to login.
    :ivar pwd_hash: Password is stored after being salted and hashed.
    :ivar institution: Name of the institution of the user. 
    :ivar allowed_group: Optional allowed user group of the user vertex, as a list of UserGroup attributes.
    """

    category: str = "user"

    uname: str
    pwd_hash: str
    institution: str
    allowed_group: List[UserGroup] = None

    def __new__(
        cls, uname: str, pwd_hash: str, institution: str, allowed_group: List[UserGroup] = None, id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        """
        Return a User instance given the desired attributes.

        :param uname: Name used by the user to login.
        :type uname: str

        :param pwd_hash: Password is stored after being salted and hashed.
        :type pwd_hash: str

        :param institution: Name of the institution of the user.
        :type institution: str

        :param allowed_group: The UserGroup instance representing the groups the user is in.
        :type user_group: List[UserGroup]

        :param id: The serverside ID of the User, defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int,optional 
        """
        if id is not VIRTUAL_ID_PLACEHOLDER and id in _vertex_cache:
            return _vertex_cache[id]

        else:
            return object.__new__(cls)

    def __init__(
            self, uname: str, pwd_hash: str, institution: str, allowed_group: List[UserGroup] = None, id: int = VIRTUAL_ID_PLACEHOLDER):
        """
        Initialize a User instance given the desired attributes.

        :param uname: Name used by the user to login.
        :type uname: str

        :param pwd_hash: Password is stored after being salted and hashed.
        :type pwd_hash: str

        :param institution: Name of the institution of the user.
        :type institution: str

        :param allowed_group: The UserGroup instance representing the groups the user is in.
        :type user_group: List[UserGroup]

        :param id: The serverside ID of the User, defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int,optional 
        """

        self.uname = uname
        self.pwd_hash = pwd_hash
        self.institution = institution
        self.allowed_group = allowed_group

        Vertex.__init__(self, id=id)

    def add(self):
        """Add this user to the serverside.
        """

        # If already added, raise an error!
        if self.added_to_db():
            raise VertexAlreadyAddedError(
                f"User with username {self.uname}" +
                "already exists in the database."
            )

        attributes = {
            'uname': self.uname,
            'pwd_hash': self.pwd_hash,
            'institution': self.institution
        }

        Vertex.add(self, attributes)

        if self.allowed_group is not None:

            for gtype in self.allowed_group:

                if not gtype.added_to_db():
                    gtype.add()

                e = RelationUserAllowedGroup(
                    inVertex=gtype,
                    outVertex=self
                )

                e.add()

    def added_to_db(self) -> bool:
        """Return whether this User is added to the database, that is, whether the ID is not the virtual ID placeholder and perform a query to the database if the vertex has already been added.

        :return: True if element is added to database, False otherwise.
        rtype: bool
        """

        return (
            self.id() != VIRTUAL_ID_PLACEHOLDER or (
                g.V().has('category', User.category).has(
                    'uname', self.uname).count().next() > 0
            )
        )

    @classmethod
    def _attrs_to_user(
            cls, uname: str, pwd_hash: str, institution: str, allowed_group: List[UserGroup] = None, id: int = VIRTUAL_ID_PLACEHOLDER):
        """Given the id and attributes of a User, see if one exists in the cache. If so, return the cached User. Otherwise, create a new one, cache it, and return it.

        :param uname: Name used by the user to login.
        :type uname: str

        :param pwd_hash: Password is stored after being salted and hashed.
        :type pwd_hash: str

        :param institution: Name of the institution of the user.
        :type institution: str

        :param allowed_group: The UserGroup instance representing the groups the user is in.
        :type user_group: List[UserGroup]

        :param id: The serverside ID of the User, defaults to VIRTUAL_ID_PLACEHOLDER
        :type id: int,optional 
        """

        if id not in _vertex_cache:
            Vertex._cache_vertex(
                User(
                    uname=uname,
                    pwd_hash=pwd_hash,
                    institution=institution,
                    allowed_group=allowed_group,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_db(cls, uname: str):
        """Query the database and return a User instance based on uname

        :param uname: Name used by the user to login.
        :type uname: str 
        """

        try:
            d = g.V().has('category', User.category).has('uname', uname) \
                .project('id', 'attrs', 'group_ids').by(__.id_()) \
                .by(__.valueMap()) \
                .by(__.both(RelationUserAllowedGroup.category).id_().fold()) \
                .next()
        except StopIteration:
            raise UserNotAddedError

        # to access attributes from attrs, do attrs[...][0]
        id, attrs, gtype_ids = d['id'], d['attrs'], d['group_ids']

        if id not in _vertex_cache:

            gtypes = []

            for gtype_id in gtype_ids:
                gtypes.append(UserGroup.from_id(gtype_id))

            Vertex._cache_vertex(
                User(
                    uname=uname,
                    pwd_hash=attrs['pwd_hash'][0],
                    institution=attrs['institution'][0],
                    allowed_group=gtypes,
                    id=id
                )
            )

        return _vertex_cache[id]

    @classmethod
    def from_id(cls, id: int):
        """Query the database and return a User instance based on the ID.

        :param id: The serverside ID of the User instance vertex.
        type id: int
        :return: Return a User from that ID.
        rtype: User
        """

        if id not in _vertex_cache:

            d = g.V(id).project('attrs', 'group_ids').by(__.valueMap()).by(
                __.both(RelationUserAllowedGroup.category).id_().fold()).next()

            # to access attributes from attrs, do attrs[...][0]

            attrs, gtype_ids = d['attrs'], d['group_ids']

            gtypes = []

            for gtype_id in gtype_ids:
                gtypes.append(UserGroup.from_id(gtype_id))

            Vertex._cache_vertex(
                User(
                    uname=attrs['uname'][0],
                    pwd_hash=attrs['pwd_hash'][0],
                    institution=attrs['institution'][0],
                    allowed_group=gtypes,
                    id=id
                )
            )

        return _vertex_cache[id]


###############################################################################
#                                   EDGES                                     #
###############################################################################


class RelationConnection(TimestampedEdge):
    """Representation of a "rel_connection" edge.
    """
    category: str = "rel_connection"

class RelationProperty(TimestampedEdge):
    """Representation of a "rel_property" edge.
    """
    category: str = "rel_property"

class RelationVersion(Edge):
    """
    Representation of a "rel_version" edge.
    """

    category: str = "rel_version"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(self=self, id=id,
                      inVertex=inVertex, outVertex=outVertex)

    def _add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationVersionAllowedType(Edge):
    """
    Representation of a "rel_version_allowed_type" edge.
    """

    category: str = "rel_version_allowed_type"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(self=self, id=id,
                      inVertex=inVertex, outVertex=outVertex,
                      )

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationComponentType(Edge):
    """
    Representation of a "rel_component_type" edge.
    """

    category: str = "rel_component_type"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(self=self, id=id,
                      inVertex=inVertex, outVertex=outVertex)

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationSubcomponent(Edge):
    """
    Representation of a "rel_subcomponent" edge.
    """

    category: str = "rel_subcomponent"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(self=self, id=id,
                      inVertex=inVertex, outVertex=outVertex)

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationPropertyType(Edge):
    """
    Representation of a "rel_property_type" edge.
    """

    category: str = "rel_property_type"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationPropertyAllowedType(Edge):
    """
    Representation of a "rel_property_allowed_type" edge.
    """

    category: str = "rel_property_allowed_type"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationFlagComponent(Edge):
    """
    Representation of a "rel_flag_component" edge.
    """

    category: str = "rel_flag_component"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside."""

        Edge.add(self, attributes={})


class RelationFlagType(Edge):
    """
    Representation of a "rel_flag_type" edge.
    """

    category: str = "rel_flag_type"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside."""

        Edge.add(self, attributes={})


class RelationFlagSeverity(Edge):
    """
    Representation of a "rel_flag_severity" edge.
    """

    category: str = "rel_flag_severity"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside."""

        Edge.add(self, attributes={})


class RelationUserAllowedGroup(Edge):
    """
    Representation of a "rel_user_group" edge.
    """

    category: str = "rel_user_group"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})


class RelationGroupAllowedPermission(Edge):
    """
    Representation of a "rel_group_permission" edge.
    """

    category: str = "rel_group_permission"

    def __init__(
        self, inVertex: Vertex, outVertex: Vertex,
        id: int = VIRTUAL_ID_PLACEHOLDER
    ):
        Edge.__init__(
            self=self, id=id,
            inVertex=inVertex, outVertex=outVertex
        )

    def add(self):
        """Add this relation to the serverside.
        """

        Edge.add(self, attributes={})
