# Flask Neo4j CRUD Application

This project is a simple CRUD (Create, Read, Update, Delete) application built using Flask and Neo4j. The application allows you to manage authors and their books in a graph database.

## Project Structure

. ├── app.py ├── requirements.txt ├── static/ │ └── index_book.html ├── venv/ │ ├── bin/ │ ├── include/ │ ├── lib/ │ └── pyvenv.cfg └── README.md


## Setup

1. **Clone the repository:**

    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. **Create a virtual environment:**

    ```sh
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install dependencies:**

    ```sh
    pip install -r requirements.txt
    ```

4. **Set environment variables:**

    Create a `.env` file in the root directory and add the following:

    ```env
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=USERNAME
    NEO4J_PASSWORD=PASSWORD
    NEO4J_DATABASE=DATABASE
    PORT=8080
    ```

5. **Run the application:**

    ```sh
    python app.py
    ```

## Endpoints

- **GET /**: Serve the static `index_book.html` file.
- **GET /books**: Retrieve a list of books.
- **GET /authors**: Retrieve a list of authors.
- **POST /write**: Create a relationship between an author and a book.
- **POST /author**: Create a new author.

## Example Usage

### Create an Author

```sh
curl -X POST -H "Content-Type: application/json" -d '{"name": "New Author", "books": ["New Book"]}' http://localhost:8080/author