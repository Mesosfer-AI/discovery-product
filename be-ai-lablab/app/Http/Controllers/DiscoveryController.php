<?php

namespace App\Http\Controllers;

use App\Http\Requests\DiscoverProductsRequest;
use App\Services\DiscoveryService;
use Illuminate\Http\JsonResponse;

class DiscoveryController extends Controller
{
    public function __invoke(DiscoverProductsRequest $request, DiscoveryService $discovery): JsonResponse
    {
        // Let the HTTP client time out before PHP terminates the request.
        set_time_limit(config('services.ai.timeout') + 10);

        $result = $discovery->discover($request->validated());

        return response()->json($result['body'], $result['status']);
    }
}
