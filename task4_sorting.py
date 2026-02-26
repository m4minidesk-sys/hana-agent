#!/usr/bin/env python3
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def bubble_sort(arr):
    arr = arr.copy()
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

def quick_sort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quick_sort(left) + middle + quick_sort(right)

def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result

def benchmark_sort(algo_name, algo_func, data):
    start = time.time()
    algo_func(data)
    return algo_name, time.time() - start

def main():
    start_time = time.time()
    print(f"[{datetime.now()}] Task 4: Sorting benchmark started")
    
    algorithms = [
        ("bubble_sort", bubble_sort, 5000),
        ("quick_sort", quick_sort, 50000),
        ("merge_sort", merge_sort, 50000),
        ("python_sorted", sorted, 50000)
    ]
    
    iterations = 12
    results = []
    
    for iteration in range(iterations):
        print(f"[{datetime.now()}] Iteration {iteration + 1}/{iterations}")
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for name, func, size in algorithms:
                data = [random.randint(0, 100000) for _ in range(size)]
                futures.append(executor.submit(benchmark_sort, name, func, data))
            
            for future in futures:
                name, duration = future.result()
                results.append({"algorithm": name, "duration": duration})
                print(f"  {name}: {duration:.3f}s")
    
    elapsed = time.time() - start_time
    
    output = {
        "task": "sorting_benchmark",
        "iterations": iterations,
        "results": results,
        "execution_time_seconds": elapsed,
        "timestamp": datetime.now().isoformat()
    }
    
    with open("task4_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[{datetime.now()}] Task 4 completed in {elapsed:.2f}s")

if __name__ == "__main__":
    main()
