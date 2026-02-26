#!/usr/bin/env python3
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def is_prime(n):
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True

def find_primes_range(start, end, results, lock):
    primes = [n for n in range(start, end) if is_prime(n)]
    with lock:
        results.extend(primes)
    return len(primes)

def main():
    start_time = time.time()
    print(f"[{datetime.now()}] Task 1: Prime calculation started")
    
    results = []
    lock = threading.Lock()
    ranges = [(1000, 10000), (10000, 20000), (20000, 30000), (30000, 40000), (40000, 50000)]
    
    # Run multiple iterations to extend execution time
    for iteration in range(10):
        print(f"[{datetime.now()}] Iteration {iteration + 1}/10")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(find_primes_range, start, end, results, lock) 
                      for start, end in ranges]
            for future in futures:
                future.result()
    
    elapsed = time.time() - start_time
    
    output = {
        "task": "prime_calculation",
        "total_primes": len(set(results)),
        "execution_time_seconds": elapsed,
        "iterations": 10,
        "range": "1000-50000",
        "timestamp": datetime.now().isoformat()
    }
    
    with open("task1_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[{datetime.now()}] Task 1 completed in {elapsed:.2f}s")
    print(f"Found {output['total_primes']} unique primes")

if __name__ == "__main__":
    main()
