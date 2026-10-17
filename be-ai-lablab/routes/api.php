<?php

use App\Http\Controllers\DiscoveryController;
use Illuminate\Support\Facades\Route;

Route::post('/v1/discover', DiscoveryController::class)->name('discovery.store');
