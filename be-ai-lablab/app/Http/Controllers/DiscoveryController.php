<?php

namespace App\Http\Controllers;

use App\Http\Requests\DiscoverProductsRequest;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class DiscoveryController extends Controller
{
    public function __invoke(DiscoverProductsRequest $request): JsonResponse
    {
        // Let the HTTP client time out before PHP terminates the request.
        set_time_limit(config('services.ai.timeout') + 10);

        try {
            $response = Http::acceptJson()
                ->asJson()
                ->connectTimeout(5)
                ->timeout(config('services.ai.timeout'))
                ->post(rtrim(config('services.ai.url'), '/').'/api/v1/discover', $request->validated());
        } catch (ConnectionException $exception) {
            report($exception);

            return response()->json(['message' => 'AI discovery is unavailable. Please try again later.'], 503);
        }

        if ($response->status() === 429) {
            return response()->json(['message' => 'Search is temporarily blocked. Please try again later.'], 429);
        }

        if (! $response->successful()) {
            Log::warning('AI discovery request failed.', ['status' => $response->status()]);

            return response()->json(['message' => 'AI discovery failed. Please try again later.'], 502);
        }

        $result = $response->json();

        if (! is_array($result) || ! isset($result['recommendations'])
            || ! is_array($result['recommendations']) || ! array_is_list($result['recommendations'])) {
            Log::warning('AI discovery returned an invalid response.');

            return response()->json(['message' => 'AI discovery returned an invalid response.'], 502);
        }

        return response()->json($result);
    }
}
