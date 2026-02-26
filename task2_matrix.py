#!/usr/bin/env python3
import json
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def matrix_multiply(size):
    A = np.random.rand(size, size)
    B = np.random.rand(size, size)
    return np.dot(A, B)

def eigenvalue_calc(size):
    M = np.random.rand(size, size)
    return np.linalg.eigvals(M)

def worker(task_id, size):
    result = matrix_multiply(size)
    eigs = eigenvalue_calc(size)
    return task_id, result.shape, len(eigs)

def main():
    start_time = time.time()
    print(f"[{datetime.now()}] Task 2: Matrix operations started")
    
    sizes = [500, 600, 700, 800]
    iterations = 8
    results = []
    
    for iteration in range(iterations):
        print(f"[{datetime.now()}] Iteration {iteration + 1}/{iterations}")
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, i, size) 
                      for i, size in enumerate(sizes)]
            for future in futures:
                results.append(future.result())
    
    elapsed = time.time() - start_time
    
    output = {
        "task": "matrix_operations",
        "operations_completed": len(results),
        "matrix_sizes": sizes,
        "iterations": iterations,
        "execution_time_seconds": elapsed,
        "timestamp": datetime.now().isoformat()
    }
    
    with open("task2_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[{datetime.now()}] Task 2 completed in {elapsed:.2f}s")

if __name__ == "__main__":
    main()
