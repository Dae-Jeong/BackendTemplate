module ProblemRendering
  extend ActiveSupport::Concern

  included do
    rescue_from StandardError, with: :render_internal_error
    rescue_from ActionDispatch::Http::Parameters::ParseError, with: :render_malformed_body
    rescue_from GreetingErrors::InvalidName, with: :render_invalid_greeting_name
    rescue_from ReservationErrors::InvalidInput, with: :render_invalid_reservation_input
    rescue_from ReservationErrors::InvalidProductId, with: :render_invalid_product_id
    rescue_from ReservationErrors::InvalidReservationId, with: :render_invalid_reservation_id
    rescue_from ReservationErrors::ProductNotFound, with: :render_product_not_found
    rescue_from ReservationErrors::NotFound, with: :render_reservation_not_found
    rescue_from ReservationErrors::SoldOut, with: :render_sold_out
    rescue_from DatabaseErrors::Busy, with: :render_database_busy
    rescue_from DatabaseErrors::PoolTimeout, with: :render_database_pool_timeout
  end

  private

  def render_malformed_body
    render_invalid_input([ "body" ], "MALFORMED_BODY")
  end

  def render_invalid_greeting_name(error)
    render_invalid_input([ "query", "name" ], error.reason)
  end

  def render_invalid_reservation_input(error)
    render_invalid_input(error.location, error.reason)
  end

  def render_invalid_product_id(error)
    render_invalid_input([ "body", "product_id" ], error.reason)
  end

  def render_invalid_reservation_id
    render_invalid_input([ "path", "reservation_id" ], "INVALID_ID")
  end

  def render_product_not_found
    render_problem(:not_found, "PRODUCT_NOT_FOUND")
  end

  def render_reservation_not_found
    render_problem(:not_found, "RESERVATION_NOT_FOUND")
  end

  def render_sold_out
    render_problem(:conflict, "SOLD_OUT")
  end

  def render_database_busy
    render_problem(:service_unavailable, "DATABASE_BUSY", retry_after: "1")
  end

  def render_database_pool_timeout
    render_problem(:service_unavailable, "DATABASE_POOL_TIMEOUT", retry_after: "1")
  end

  def render_internal_error(error)
    Rails.error.report(error, handled: true, severity: :error)
    render_problem(:internal_server_error, "INTERNAL_ERROR")
  end

  def render_invalid_input(location, reason)
    render_problem(
      :unprocessable_content,
      "INVALID_INPUT",
      errors: [ { location: location, code: reason } ]
    )
  end

  def render_problem(status, code, errors: nil, retry_after: nil)
    numeric_status = Rack::Utils.status_code(status)
    response.set_header("Retry-After", retry_after) if retry_after
    body = {
      type: "about:blank",
      title: Rack::Utils::HTTP_STATUS_CODES.fetch(numeric_status),
      status: numeric_status,
      code: code
    }
    body[:errors] = errors if errors

    render json: body, status: status, content_type: "application/problem+json"
  end
end
