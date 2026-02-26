#!/usr/bin/env python3
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def monte_carlo_pi(samples):
    inside = 0
    for _ in range(samples):
        x, y = random.random(), random.random()
        if x*x + y*y <= 1:
            inside += 1
    return inside

def main():
    start_time = time.time()
    print(f"[{datetime.now()}] Task 3: Monte Carlo simulation started")
    
    samples_per_thread = 5_000_000
    threads = 8
    iterations = 15
    pi_estimates = []
    
    for iteration in range(iterations):
        print(f"[{datetime.now()}] Iteration {iteration + 1}/{iterations}")
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(monte_carlo_pi, samples_per_thread) 
                      for _ in range(threads)]
            inside_total = sum(f.result() for f in futures)
        
        total_samples = samples_per_thread * threads
        pi_estimate = 4 * inside_total / total_samples
        pi_estimates.append(pi_estimate)
        print(f"  Pi estimate: {pi_estimate:.6f}")
    
    elapsed = time.time() - start_time
    avg_pi = sum(pi_estimates) / len(pi_estimates)
    
    output = {
        "task": "monte_carlo_pi",
        "iterations": iterations,
        "samples_per_iteration": samples_per_thread * threads,
        "average_pi_estimate": avg_pi,
        "all_estimates": pi_estimates,
        "execution_time_seconds": elapsed,
        "timestamp": datetime.now().isoformat()
    }
    
    with open("task3_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[{datetime.now()}] Task 3 completed in {elapsed:.2f}s")
    print(f"Average Pi estimate: {avg_pi:.6f}")

if __name__ == "__main__":
    main()
