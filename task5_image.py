#!/usr/bin/env python3
import json
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

def generate_image(width, height):
    return np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)

def apply_blur(image, kernel_size=5):
    h, w, c = image.shape
    result = np.zeros_like(image)
    pad = kernel_size // 2
    for i in range(pad, h - pad):
        for j in range(pad, w - pad):
            for k in range(c):
                result[i, j, k] = np.mean(
                    image[i-pad:i+pad+1, j-pad:j+pad+1, k]
                )
    return result

def edge_detection(image):
    gray = np.mean(image, axis=2).astype(np.int16)
    h, w = gray.shape
    edges = np.zeros_like(gray)
    for i in range(1, h-1):
        for j in range(1, w-1):
            gx = gray[i+1, j] - gray[i-1, j]
            gy = gray[i, j+1] - gray[i, j-1]
            edges[i, j] = min(255, int(np.sqrt(gx**2 + gy**2)))
    return edges

def process_image(task_id, width, height):
    img = generate_image(width, height)
    blurred = apply_blur(img)
    edges = edge_detection(blurred)
    return task_id, img.shape, edges.shape

def main():
    start_time = time.time()
    print(f"[{datetime.now()}] Task 5: Image processing started")
    
    sizes = [(400, 400), (500, 500), (600, 600)]
    iterations = 10
    results = []
    
    for iteration in range(iterations):
        print(f"[{datetime.now()}] Iteration {iteration + 1}/{iterations}")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_image, i, w, h) 
                      for i, (w, h) in enumerate(sizes)]
            for future in futures:
                task_id, img_shape, edge_shape = future.result()
                results.append({
                    "task_id": task_id,
                    "image_shape": img_shape,
                    "edges_shape": edge_shape
                })
    
    elapsed = time.time() - start_time
    
    output = {
        "task": "image_processing",
        "iterations": iterations,
        "image_sizes": sizes,
        "images_processed": len(results),
        "execution_time_seconds": elapsed,
        "timestamp": datetime.now().isoformat()
    }
    
    with open("task5_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"[{datetime.now()}] Task 5 completed in {elapsed:.2f}s")

if __name__ == "__main__":
    main()
