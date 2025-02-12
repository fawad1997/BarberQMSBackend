<!-- Remove-Item alembic/versions/* -Recurse -Force

# Initialize fresh migrations
alembic init alembic

# Create new migration
alembic revision --autogenerate -m "initial"

# Run migration
alembic upgrade head -->

# Barbershop Queue System API

## Setup Instructions

Follow these steps to set up and run the Barbershop Queue System API on your local machine.

### Prerequisites

- Ensure you have [Docker](https://www.docker.com/get-started) installed on your machine.
- Make sure you have [Python 3.11](https://www.python.org/downloads/release/python-3110/) installed if you are not using Docker.
- Install [PostgreSQL](https://www.postgresql.org/download/) if you plan to run the database locally.

### Clone the Repository

```bash
git clone https://github.com/fawad1997/BarberQMSBackend.git
cd BarberQMSBackend
```

### Create a `.env` File

Create a `.env` file in the root of the project directory with the following content:
```
DATABASE_URL=postgresql://postgres:admin123@localhost:5432/barbershop
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=300
ENVIRONMENT=development
```


Make sure to replace `your_secret_key` with a secure key of your choice.

### Using Docker

1. **Build the Docker Image**

   Run the following command in the project directory:

   ```bash
   docker build -t fastapi .
   ```

2. **Run the Docker Container**

   To run the application, execute:

   ```bash
   docker run --rm -it -p 8000:4000 fastapi
   ```

   This will start the FastAPI application, and you can access it at `http://localhost:8000`.

### Without Docker

If you prefer to run the application without Docker, follow these steps:

1. **Create a Virtual Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

If you are unable to run the above command, try running the following command:
```bash
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope Process
.\env\Scripts\activate  
```
	

2. **Install Dependencies**

   Make sure you have a `requirements.txt` file in your project. If it’s not present, create it with the necessary dependencies. Then run:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run Database Migrations**

   Ensure your PostgreSQL server is running, then run the following command to apply migrations:

   ```bash
   alembic upgrade head
   ```

4. **Run the Application**

   Start the FastAPI application with:

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

   You can access the API at `http://localhost:8000`.

### Accessing the API

Once the application is running, you can access the API documentation at: http://localhost:8000/docs



### Stopping the Application

If you are using Docker, you can stop the application by pressing `Ctrl + C` in the terminal where the container is running. If you are running it locally, simply stop the server with `Ctrl + C`.

### Additional Notes

- Ensure that your PostgreSQL database is set up and accessible as specified in the `.env` file.
- Modify the `DATABASE_URL` in the `.env` file if your database credentials or host differ.

Now you are ready to use the Barbershop Queue System API!