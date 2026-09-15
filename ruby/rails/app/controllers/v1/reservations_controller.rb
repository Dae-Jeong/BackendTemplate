class V1::ReservationsController < ApplicationController
  wrap_parameters false
  rescue_from ActionDispatch::Http::Parameters::ParseError, with: :render_malformed_body

  def create
    if request.headers["Idempotency-Key"].present?
      return render_invalid_input([ "header", "Idempotency-Key" ], "IDEMPOTENCY_NOT_SUPPORTED")
    end

    unknown_field = request.request_parameters.keys.map(&:to_s).find { |field| field != "product_id" }
    return render_invalid_input([ "body", unknown_field ], "UNKNOWN_FIELD") if unknown_field

    result = ReservationService.create(
      product_id: request.request_parameters["product_id"],
      clock: Rails.application.config.x.clock
    )

    render json: { data: serialize(result) }, status: :created
  rescue ReservationService::InvalidInput => error
    render_invalid_input([ "body", "product_id" ], error.reason)
  end

  def show
    result = ReservationService.find(reservation_id: params[:reservation_id])

    render json: { data: serialize(result) }
  rescue ReservationService::InvalidInput => error
    render_invalid_input([ "path", "reservation_id" ], error.reason)
  rescue ReservationService::NotFound
    render json: {
      type: "about:blank",
      title: "Not Found",
      status: 404,
      code: "RESERVATION_NOT_FOUND"
    }, status: :not_found, content_type: "application/problem+json"
  end

  private

  def serialize(result)
    {
      reservation_id: result.reservation_id,
      product_id: result.product_id,
      created_at: result.created_at.iso8601
    }
  end

  def render_malformed_body
    render_invalid_input([ "body" ], "MALFORMED_BODY")
  end

  def render_invalid_input(location, reason)
    render json: {
      type: "about:blank",
      title: "Unprocessable Content",
      status: 422,
      code: "INVALID_INPUT",
      errors: [ { location: location, code: reason } ]
    }, status: :unprocessable_content, content_type: "application/problem+json"
  end
end
