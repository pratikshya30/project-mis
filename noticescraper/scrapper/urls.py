from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('edit/<str:email_id>/', views.edit_email, name='edit_email'),
    path('delete/<str:email_id>/', views.delete_email, name='delete_email'),
    path('scrape/', views.scrape_images, name='scrape_images'),
    path('view-notices/', views.view_notices, name='view_notices'),
]
