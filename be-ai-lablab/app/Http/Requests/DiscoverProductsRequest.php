<?php

namespace App\Http\Requests;

use Illuminate\Contracts\Validation\ValidationRule;
use Illuminate\Foundation\Http\FormRequest;

class DiscoverProductsRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        return [
            'query' => ['required', 'string', 'min:2'],
            'budget_max' => ['sometimes', 'nullable', 'numeric', 'gt:0'],
            'currency' => ['sometimes', 'string', 'regex:/^[A-Z]{3}$/'],
            'limit' => ['sometimes', 'integer', 'between:1,10'],
            'preferred_stores' => ['sometimes', 'array', 'list'],
            'preferred_stores.*' => ['required', 'string'],
            'country' => ['sometimes', 'nullable', 'string', 'regex:/^[a-z]{2}$/'],
        ];
    }

    protected function prepareForValidation(): void
    {
        if (is_string($this->input('country'))) {
            $this->merge(['country' => strtolower(trim($this->input('country')))]);
        }
    }
}
