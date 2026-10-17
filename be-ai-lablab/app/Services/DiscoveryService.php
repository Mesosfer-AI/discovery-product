<?php

namespace App\Services;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class DiscoveryService
{
    /** @return array{status: int, body: array} */
    public function discover(array $query): array
    {
        try {
            $response = Http::acceptJson()
                ->asJson()
                ->connectTimeout(5)
                ->timeout(config('services.ai.timeout'))
                ->post(rtrim(config('services.ai.url'), '/').'/api/v1/discover', $query);
        } catch (ConnectionException $exception) {
            report($exception);

            return ['status' => 503, 'body' => ['message' => 'AI discovery is unavailable. Please try again later.']];
        }

        if ($response->status() === 429) {
            return ['status' => 429, 'body' => ['message' => 'Search is temporarily blocked. Please try again later.']];
        }

        if (! $response->successful()) {
            Log::warning('AI discovery request failed.', ['status' => $response->status()]);

            return ['status' => 502, 'body' => ['message' => 'AI discovery failed. Please try again later.']];
        }

        $result = $response->json();

        if (! is_array($result) || ! isset($result['recommendations'])
            || ! is_array($result['recommendations']) || ! array_is_list($result['recommendations'])) {
            Log::warning('AI discovery returned an invalid response.');

            return ['status' => 502, 'body' => ['message' => 'AI discovery returned an invalid response.']];
        }

        return ['status' => 200, 'body' => $result];
    }
}
