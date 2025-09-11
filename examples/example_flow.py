from prefect import flow, task
import time


@task
def hello_task(name: str = "Northflank"):
    """A simple task that says hello."""
    print(f"Hello from {name}!")
    return f"Greetings from {name}"


@task
def process_data(message: str):
    """Simulate some data processing."""
    print(f"Processing: {message}")
    time.sleep(2)  # Simulate work
    return f"Processed: {message.upper()}"


@flow(name="hello-northflank")
def hello_northflank_flow(name: str = "Northflank"):
    """
    A simple flow that demonstrates running on Northflank.
    """
    # Say hello
    greeting = hello_task(name)

    # Process the greeting
    result = process_data(greeting)

    print(f"Flow completed with result: {result}")
    return result


if __name__ == "__main__":
    # Run the flow locally for testing
    hello_northflank_flow()
