# Azure OpenAI Setup Guide

This guide will help you set up Azure OpenAI for the Jira Meeting Organizer.

## Prerequisites

- An active Azure subscription
- Access to Azure OpenAI Service (requires approval from Microsoft)

## Step 1: Request Access to Azure OpenAI

1. Go to https://azure.microsoft.com/en-us/products/ai-services/openai-service
2. Click "Apply for access"
3. Fill out the application form
4. Wait for approval (typically 1-3 business days)

## Step 2: Create an Azure OpenAI Resource

1. Log in to the [Azure Portal](https://portal.azure.com)
2. Click "Create a resource"
3. Search for "Azure OpenAI"
4. Click "Create"
5. Fill in the required information:
   - **Subscription**: Select your subscription
   - **Resource group**: Create new or use existing
   - **Region**: Choose a region (e.g., East US, West Europe)
   - **Name**: Give your resource a unique name (e.g., `my-company-openai`)
   - **Pricing tier**: Select Standard S0
6. Click "Review + create" then "Create"
7. Wait for deployment to complete

## Step 3: Deploy a Model

1. Navigate to your Azure OpenAI resource in the Azure Portal
2. Click on "Go to Azure OpenAI Studio" or visit https://oai.azure.com/
3. In Azure OpenAI Studio, go to "Deployments" in the left menu
4. Click "+ Create new deployment"
5. Configure the deployment:
   - **Model**: Select `gpt-4` or `gpt-4-32k` (recommended for this application)
   - **Deployment name**: Give it a name (e.g., `gpt-4-deployment`)
     - **Important**: Remember this name, you'll need it for the configuration
   - **Model version**: Select the latest version
   - **Deployment type**: Standard
6. Click "Create"

> **Note**: You can also use `gpt-35-turbo` if GPT-4 is not available, but GPT-4 provides better analysis quality.

## Step 4: Get Your API Credentials

### Get the API Key

1. In the Azure Portal, navigate to your Azure OpenAI resource
2. In the left menu, click on "Keys and Endpoint"
3. You'll see two keys (KEY 1 and KEY 2) - copy either one
4. Keep this key secure!

### Get the Endpoint

On the same "Keys and Endpoint" page, you'll see the endpoint URL. It will look like:
```
https://your-resource-name.openai.azure.com/
```

Copy this URL (including the trailing slash).

### Get the API Version

The current recommended API version is `2024-02-15-preview`. This is already set as the default in the application.

## Step 5: Configure the Application

1. Open your backend `.env` file
2. Update the following variables with your credentials:

```env
AZURE_OPENAI_API_KEY=<your-api-key-from-step-4>
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=<your-deployment-name-from-step-3>
```

**Example:**
```env
AZURE_OPENAI_API_KEY=1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
AZURE_OPENAI_ENDPOINT=https://my-company-openai.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4-deployment
```

## Step 6: Verify the Setup

1. Start your backend server:
   ```bash
   cd backend
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   uvicorn server:app --reload --port 8000
   ```

2. Check the logs for any errors related to Azure OpenAI

3. Try creating a new analysis through the frontend to verify the integration works

## Common Issues and Solutions

### Issue: "Resource not found" error

**Solution**:
- Verify your endpoint URL is correct
- Ensure the endpoint includes `https://` and ends with `/`
- Check that your resource is in the correct region

### Issue: "Deployment not found" error

**Solution**:
- Verify your deployment name matches exactly what you created in Azure OpenAI Studio
- Deployment names are case-sensitive

### Issue: "Authentication failed" error

**Solution**:
- Verify your API key is correct (no extra spaces)
- Try using the other key (KEY 2 instead of KEY 1)
- Check that your Azure subscription is active

### Issue: "Rate limit exceeded" error

**Solution**:
- Azure OpenAI has rate limits based on your pricing tier
- Check your quota in Azure OpenAI Studio under "Quotas"
- Consider upgrading your pricing tier if needed

### Issue: "Model deployment is not available" error

**Solution**:
- Your deployment might still be provisioning - wait a few minutes
- Check the deployment status in Azure OpenAI Studio
- Ensure the model is deployed in the same region as your resource

## Rate Limits and Quotas

Azure OpenAI has rate limits based on tokens per minute (TPM) and requests per minute (RPM):

| Model | Default TPM | Default RPM |
|-------|-------------|-------------|
| GPT-4 | 40,000 | 600 |
| GPT-4-32k | 80,000 | 600 |
| GPT-3.5-Turbo | 120,000 | 720 |

For production use, you may need to request quota increases through Azure Support.

## Cost Considerations

Azure OpenAI pricing is based on token usage:

| Model | Price per 1K tokens (Input) | Price per 1K tokens (Output) |
|-------|----------------------------|------------------------------|
| GPT-4 | $0.03 | $0.06 |
| GPT-4-32k | $0.06 | $0.12 |
| GPT-3.5-Turbo | $0.0015 | $0.002 |

**Estimated cost per analysis**: $0.05 - $0.20 depending on:
- Number of existing tickets in the project
- Length of meeting minutes
- Model used (GPT-4 vs GPT-3.5)

Monitor your usage in Azure Portal under "Cost Management + Billing"

## Best Practices

1. **Use Key Vault**: For production, store your API keys in Azure Key Vault
2. **Monitor Usage**: Set up budget alerts in Azure to track costs
3. **Implement Caching**: Cache ticket data to reduce API calls
4. **Error Handling**: Implement retry logic for transient failures
5. **Rate Limiting**: Implement application-level rate limiting to stay within quotas

## Additional Resources

- [Azure OpenAI Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- [Azure OpenAI Pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
- [OpenAI Python SDK Documentation](https://github.com/openai/openai-python)
- [Azure OpenAI Studio](https://oai.azure.com/)

## Support

If you encounter issues:

1. Check the [Azure Status Page](https://status.azure.com/)
2. Review Azure OpenAI service health in Azure Portal
3. Contact Azure Support through the Azure Portal
4. Open an issue on the project GitHub repository

---

**Security Note**: Never commit your API keys to version control. Always use environment variables and keep your `.env` file in `.gitignore`.
