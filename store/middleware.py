from subscriptions.models import StoreProfile

class SubdomainMaskingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # URL ka host pakdein (e.g., 'vermapharmacy.localhost:8000' ya '127.0.0.1:8000')
        host = request.get_host().lower()

        # Main domain ko ignore kre
        standard_hosts = ['127.0.0.1:8000', 'localhost:8000', 'DawaiSetu.com', 'www.DawaiSetu.com']

        if host not in standard_hosts:
            
            # Phle Port number hatayein (:8000 hta dega)
            domain_without_port = host.split(':')[0] 
             
            # Subdomain nikal le ('vermapahrmacy)
            subdomain = domain_without_port.split('.')[0]
            
            # Check kre ki iss naam se koi seller h kya
            profile = StoreProfile.objects.filter(custom_subdomain=subdomain).first()
            
            if profile:
                # Bina URL change kiye seller ko lock kr dein! (Masking)
                request.session['locked_seller_id'] = str(profile.user.id)
                
                # Note: Aapka landing_page view is session ko automatically padh lega

        response = self.get_response(request)
        return response

