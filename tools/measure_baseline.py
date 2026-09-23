import psutil
import time
import os
import sys
from pathlib import Path

def measure_baseline(duration_seconds=30, sample_interval=1.0):
    process = psutil.Process(os.getpid())
    
    print("=" * 60)
    print("Stage 3F Baseline Performance Measurement")
    print("=" * 60)
    print(f"Duration: {duration_seconds}s")
    print(f"Sample interval: {sample_interval}s")
    print()
    
    rss_initial = process.memory_info().rss / 1024 / 1024
    threads_initial = process.num_threads()
    print("Initial state (cold start):")
    print(f"  RSS: {rss_initial:.1f} MB")
    print(f"  Threads: {threads_initial}")
    print()
    
    print("Warming up for 5 seconds...")
    time.sleep(5)
    
    print(f"Collecting samples for {duration_seconds}s...")
    rss_samples = []
    cpu_samples = []
    
    start_time = time.time()
    while time.time() - start_time < duration_seconds:
        rss = process.memory_info().rss / 1024 / 1024
        cpu = process.cpu_percent(interval=sample_interval)
        
        rss_samples.append(rss)
        cpu_samples.append(cpu)
        
        elapsed = time.time() - start_time
        print(f"  [{elapsed:5.1f}s] RSS: {rss:6.1f} MB, CPU: {cpu:5.1f}%", end="\r")
    
    print()
    print()
    
    rss_mean = sum(rss_samples) / len(rss_samples)
    rss_median = sorted(rss_samples)[len(rss_samples) // 2]
    rss_peak = max(rss_samples)
    
    cpu_mean = sum(cpu_samples) / len(cpu_samples)
    cpu_median = sorted(cpu_samples)[len(cpu_samples) // 2]
    cpu_peak = max(cpu_samples)
    
    threads_final = process.num_threads()
    
    print("=" * 60)
    print("Results")
    print("=" * 60)
    print()
    print("Memory (RSS):")
    print(f"  Initial:  {rss_initial:6.1f} MB")
    print(f"  Mean:     {rss_mean:6.1f} MB")
    print(f"  Median:   {rss_median:6.1f} MB")
    print(f"  Peak:     {rss_peak:6.1f} MB")
    print()
    print("CPU Usage:")
    print(f"  Mean:     {cpu_mean:5.1f}%")
    print(f"  Median:   {cpu_median:5.1f}%")
    print(f"  Peak:     {cpu_peak:5.1f}%")
    print()
    print("Threads:")
    print(f"  Initial:  {threads_initial}")
    print(f"  Final:    {threads_final}")
    print()
    print("=" * 60)
    print()
    
    output_file = Path(__file__).parent / "baseline_metrics.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Stage 3F Baseline Metrics\n")
        f.write("=" * 60 + "\n")
        f.write(f"Initial RSS: {rss_initial:.1f} MB\n")
        f.write(f"Mean RSS: {rss_mean:.1f} MB\n")
        f.write(f"Median RSS: {rss_median:.1f} MB\n")
        f.write(f"Peak RSS: {rss_peak:.1f} MB\n")
        f.write(f"Mean CPU: {cpu_mean:.1f}%\n")
        f.write(f"Median CPU: {cpu_median:.1f}%\n")
        f.write(f"Peak CPU: {cpu_peak:.1f}%\n")
        f.write(f"Initial threads: {threads_initial}\n")
        f.write(f"Final threads: {threads_final}\n")
    
    print(f"Metrics saved to: {output_file}")
    print()

if __name__ == "__main__":
    measure_baseline()
