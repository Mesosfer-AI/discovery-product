<?php

namespace App\Jobs;

use App\Services\DiscoveryService;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Support\Facades\Cache;
use Throwable;

class DiscoverProducts implements ShouldQueue
{
    use Queueable;

    public int $tries = 1;

    public int $timeout;

    public bool $failOnTimeout = true;

    public function __construct(public string $id, public array $query)
    {
        $this->onConnection('discovery')->onQueue('discovery');
        $this->timeout = config('services.ai.timeout') + 10;
    }

    public function handle(DiscoveryService $discovery): void
    {
        $cache = Cache::store('database');
        if ($cache->get('discovery:'.$this->id) === null) {
            return;
        }

        $cache->put('discovery:'.$this->id, ['status' => 'processing'], now()->addHour());
        $result = $discovery->discover($this->query);
        $cache->put('discovery:'.$this->id, $result['status'] === 200
            ? ['status' => 'completed', 'result' => $result['body']]
            : ['status' => 'failed', 'error_status' => $result['status']], now()->addHour());
    }

    public function failed(?Throwable $exception): void
    {
        Cache::store('database')->put('discovery:'.$this->id,
            ['status' => 'failed', 'error_status' => 503], now()->addHour());
    }
}
