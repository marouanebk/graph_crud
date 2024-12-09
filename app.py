#!/usr/bin/env python
import logging
import os
from json import dumps
from textwrap import dedent
from typing import cast

import neo4j
from flask import Flask, Response, request
from neo4j import GraphDatabase, basic_auth
from typing_extensions import LiteralString

app = Flask(__name__, static_url_path="/static/")

url = os.getenv("NEO4J_URI", "bolt://localhost:7687")
username = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "password123")
# neo4j_version = os.getenv("NEO4J_VERSION", "4")
database = os.getenv("NEO4J_DATABASE", "neo4j")

port = int(os.getenv("PORT", 8080))

driver = GraphDatabase.driver(url, auth=basic_auth(username, password))


def query(q: LiteralString) -> LiteralString:
    # this is a safe transform:
    # no way for cypher injection by trimming whitespace
    # hence, we can safely cast to LiteralString
    return cast(LiteralString, dedent(q).strip())


@app.route("/")
def get_index():
    return app.send_static_file("index_book.html")


def serialize_book(book):
    return {
        "id": book["id"],
        "title": book["title"],
        "summary": book["summary"],
        "released": book["released"],
        "genre": book["genre"],
        "rated": book["rated"],
        "tagline": book["tagline"],
        "votes": book.get("votes", 0)
    }

def serialize_author(author):
    return {
        "name": author[0],
        "job": author[1],
        "role": author[2]
    }


@app.route("/graph")
# def get_graph():
#     records, _, _ = driver.execute_query(
#         query("""
#             MATCH (b:Book)<-[:WROTE]-(a:Author)
#             RETURN b.title AS book, collect(a.name) AS authors
#             LIMIT $limit
#         """),
#         database_=database,
#         routing_="r",
#         limit=request.args.get("limit", 100)
#     )
#     nodes = []
#     rels = []
#     i = 0
#     for record in records:
#         nodes.append({"title": record["book"], "label": "book"})
#         target = i
#         i += 1
#         for name in record["authors"]:
#             author = {"title": name, "label": "author"}
#             try:
#                 source = nodes.index(author)
#             except ValueError:
#                 nodes.append(author)
#                 source = i
#                 i += 1
#             rels.append({"source": source, "target": target})
#     return Response(dumps({"nodes": nodes, "links": rels}),
#                     mimetype="application/json")
@app.route("/graph")
def get_graph():
    records, _, _ = driver.execute_query(
        query("""
            MATCH (b:Book)
            OPTIONAL MATCH (b)<-[:WROTE]-(a:Author)
            RETURN b.title AS book, collect(a.name) AS authors
        """),
        database_=database,
        routing_="r",
        limit=request.args.get("limit", 100)
    )
    nodes = []
    rels = []
    i = 0
    for record in records:
        book_node = {"title": record["book"], "label": "book"}
        if book_node not in nodes:
            nodes.append(book_node)
        target = nodes.index(book_node)
        for name in record["authors"]:
            if name:
                author_node = {"title": name, "label": "author"}
                if author_node not in nodes:
                    nodes.append(author_node)
                source = nodes.index(author_node)
                rels.append({"source": source, "target": target})
    return Response(dumps({"nodes": nodes, "links": rels}),
                    mimetype="application/json")

@app.route("/search")
def get_search():
    try:
        q = request.args["q"]
    except KeyError:
        return []
    else:
        records, _, _ = driver.execute_query(
            query("""
                MATCH (book:Book)
                WHERE toLower(book.title) CONTAINS toLower($title)
                RETURN book
            """),
            title=q,
            database_=database,
            routing_="r",
        )
        return Response(
            dumps([serialize_book(record["book"]) for record in records]),
            mimetype="application/json"
        )


@app.route("/book/<title>")
def get_book(title):
    result = driver.execute_query(
        query("""
            MATCH (book:Book {title:$title})
            OPTIONAL MATCH (book)<-[r]-(author:Author)
            RETURN book,
            COLLECT([author.name, author.job, r.role]) AS authors
            LIMIT 1
        """),
        title=title,
        database_=database,
        routing_="r",
        result_transformer_=neo4j.Result.single,
    )
    
    if not result:
        return Response(dumps({"error": "Book not found"}), status=404,
                      mimetype="application/json")

    book = result["book"]
    return Response(dumps({
        "title": book["title"],
        "summary": book.get("summary", ""),
        "genre": book.get("genre", ""),
        "released": book.get("released", ""),
        "rated": book.get("rated", ""),
        "tagline": book.get("tagline", ""),
        "authors": [serialize_author(member) for member in result["authors"]]
    }), mimetype="application/json")

@app.route("/book/<title>/vote", methods=["POST"])
def vote_in_book(title):
    summary = driver.execute_query(
        query("""
            MATCH (b:Book {title: $title})
            SET b.votes = coalesce(b.votes, 0) + 1;
        """),
        database_=database,
        title=title,
        result_transformer_=neo4j.Result.consume,
    )
    updates = summary.counters.properties_set
    return Response(dumps({"updates": updates}), mimetype="application/json")

@app.route("/book", methods=["POST"])
def add_book():
    try:
        data = request.get_json()
        title = data["title"]
        summary = data.get("summary", "")
        released = data.get("released", "")
        genre = data.get("genre", "")
        rated = data.get("rated", "")
        tagline = data.get("tagline", "")

        summary_result = driver.execute_query(
            query("""
                CREATE (b:Book {
                    title: $title,
                    summary: $summary,
                    released: $released,
                    genre: $genre,
                    rated: $rated,
                    tagline: $tagline
                })
            """),
            title=title,
            summary=summary,
            released=released,
            genre=genre,
            rated=rated,
            tagline=tagline,
            database_=database,
            result_transformer_=neo4j.Result.consume,
        )
        updates = summary_result.counters.nodes_created

        return Response(dumps({"message": "Book added successfully", "updates": updates}),
                        mimetype="application/json")
    except KeyError as e:
        return Response(dumps({"error": f"Missing required field: {str(e)}"}), status=400,
                        mimetype="application/json")
    except Exception as e:
        return Response(dumps({"error": str(e)}), status=500, mimetype="application/json")

#  Sample data
books_data = [
    {
        "title": "The Great Gatsby",
        "summary": "A story of decadence and excess, exploring the American Dream.",
        "released": "1925",
        "genre": "Classic Fiction",
        "rated": "4.5",
        "tagline": "The story of the fabulously wealthy Jay Gatsby"
    },
    {
        "title": "1984",
        "summary": "A dystopian social science fiction novel and cautionary tale.",
        "released": "1949",
        "genre": "Science Fiction",
        "rated": "4.8",
        "tagline": "Big Brother is watching you"
    },
    {
        "title": "Pride and Prejudice",
        "summary": "A romantic novel of manners.",
        "released": "1813",
        "genre": "Romance",
        "rated": "4.7",
        "tagline": "A classic of English literature"
    },
    {
        "title": "The Hobbit",
        "summary": "A fantasy novel about the adventures of Bilbo Baggins.",
        "released": "1937",
        "genre": "Fantasy",
        "rated": "4.6",
        "tagline": "There and back again"
    },
    {
        "title": "To Kill a Mockingbird",
        "summary": "A story of racial injustice and loss of innocence.",
        "released": "1960",
        "genre": "Fiction",
        "rated": "4.9",
        "tagline": "The unforgettable novel of a childhood in a sleepy Southern town"
    },
     {
        "title": "Foundation",
        "summary": "A complex saga of humans scattered on planets throughout the galaxy all living under the rule of the Galactic Empire.",
        "released": "1951",
        "genre": "Science Fiction",
        "rated": "4.7",
        "tagline": "The epic saga of the Foundation"
    },
    {
        "title": "I, Robot",
        "summary": "A collection of short stories about the interaction of humans, robots, and morality.",
        "released": "1950",
        "genre": "Science Fiction",
        "rated": "4.6",
        "tagline": "The classic collection of robot stories"
    }
]

authors_data = [
    {"name": "F. Scott Fitzgerald", "books": ["The Great Gatsby"]},
    {"name": "George Orwell", "books": ["1984"]},
    {"name": "Jane Austen", "books": ["Pride and Prejudice"]},
    {"name": "J.R.R. Tolkien", "books": ["The Hobbit"]},
    {"name": "Harper Lee", "books": ["To Kill a Mockingbird"]},
    {"name": "Isaac Asimov", "books": ["Foundation", "I, Robot"]}

]

def create_data(driver):
    with driver.session(database=database) as session:
        # Clear existing data
        session.run("MATCH (n) DETACH DELETE n")
        
        # Create books
        for book in books_data:
            session.run("""
                CREATE (b:Book {
                    title: $title,
                    summary: $summary,
                    released: $released,
                    genre: $genre,
                    rated: $rated,
                    tagline: $tagline,
                    votes: 0
                })
            """, **book)
        
        # Create authors and relationships
        for author in authors_data:
            session.run("""
                MERGE (a:Author {name: $name})
                WITH a
                UNWIND $books as book
                MATCH (b:Book {title: book})
                CREATE (a)-[:WROTE {roles: ['Author']}]->(b)
            """, **author)

        print("Sample data created successfully!")

@app.route("/books", methods=["GET"])
def get_books():
    records, _, _ = driver.execute_query(
        """
        MATCH (b:Book)
        RETURN b.title AS title
        ORDER BY b.title
        """,
        database_=database,
    )
    
    books = [record["title"] for record in records]
    return Response(dumps(books), mimetype="application/json")


@app.route("/authors", methods=["GET"])
def get_authors():
    records, _, _ = driver.execute_query(
        """
        MATCH (a:Author)
        RETURN a.name AS name, a.job AS job
        ORDER BY a.name
        """,
        database_=database,
    )
    
    authors = [{"name": record["name"], "job": record["job"]} for record in records]
    return Response(dumps(authors), mimetype="application/json")

@app.route("/write", methods=["POST"])
def create_wrote_relationship():
    try:
        data = request.json
        
        records, _, _ = driver.execute_query(
            """
            MATCH (a:Author {name: $authorName})
            MATCH (b:Book {title: $bookTitle})
            CREATE (a)-[r:WROTE {role: $role}]->(b)
            RETURN a, b, r
            """,
            data,
            database_=database,
        )
        
        return Response(dumps({"message": "Relationship created successfully"}), 
                       mimetype="application/json")
    except Exception as e:
        return Response(dumps({"error": str(e)}), 
                       status=400, 
                       mimetype="application/json")
    
@app.route("/author", methods=["POST"])
def create_author():
    try:
        data = request.json
        print("Received author data:", data)  # Debug log

        def create_author_tx(tx, author_data):
            # Create author
            result = tx.run("""
                CREATE (a:Author {
                    name: $name,
                    job: $job,
                    bio: $bio
                })
                RETURN a
            """, author_data)
            
            # If a book is specified, create the relationship
            if author_data.get('linkToBook'):
                print(f"Creating relationship with book: {author_data['linkToBook']}")  # Debug log
                tx.run("""
                    MATCH (a:Author {name: $name})
                    MATCH (b:Book {title: $linkToBook})
                    CREATE (a)-[:WROTE {role: $role}]->(b)
                """, author_data)
            
            return result.single()

        with driver.session() as session:
            result = session.execute_write(create_author_tx, data)
            return Response(dumps({"message": "Author created successfully"}), 
                          mimetype="application/json")
    except Exception as e:
        print("Error creating author:", str(e))  # Debug log
        return Response(dumps({"error": str(e)}), 
                       status=400, 
                       mimetype="application/json")
if __name__ == "__main__":
    logging.root.setLevel(logging.INFO)
    logging.info("Starting on port %d, database is at %s", port, url)
    try:
        # create_data(driver)  # This will create your sample data
        logging.info("Sample data created successfully!")
        
    
        app.run(port=port)
    finally:
        driver.close()

